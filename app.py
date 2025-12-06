# app.py
import os
import re
import json
import requests
from functools import wraps
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    session, abort, send_from_directory
)
from werkzeug.utils import secure_filename

# Optional: Firestore
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False

# Optional: document parsing libs (light usage)
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    import docx
except Exception:
    docx = None
try:
    import pandas as pd
except Exception:
    pd = None

# OpenAI
try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
    OPENAI_AVAILABLE = bool(OPENAI_API_KEY)
except Exception:
    openai = None
    OPENAI_AVAILABLE = False

# SerpAPI key (for real web search fallback)
SERPAPI_KEY = os.getenv("SERPAPI_KEY")  # set in env, do NOT hardcode

# Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# Upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}

# -------------------------
# In-memory / Firestore init
# -------------------------
# In-memory datasets (fallback)
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "bithu": {"password": "Test@123", "role": "bithu", "name": "Bí thư Chi bộ"},
    "user_demo": {"password": "Test@123", "role": "dangvien", "name": "User Demo"},
    "dv01": {"password": "Test@123", "role": "dangvien", "name": "Đảng viên 01"},
}

# In-memory storage (fallback)
DOCS = {}         # filename -> {"summary","content","uploader"}
CHAT_HISTORY = {} # username -> [{"question","answer"}...]
NHAN_XET = {}     # per dang vien code -> text
SINH_HOAT = []    # chung chi bo
CHI_BO_INFO = {}  # e.g. {"baso": "...", "name": "Chi bộ X"}

# Firestore client (if available & credentials)
FS_CLIENT = None
if FIRESTORE_AVAILABLE:
    try:
        FS_CLIENT = firestore.Client()
    except Exception:
        FS_CLIENT = None

# -------------------------
# Utilities
# -------------------------
def login_required(role=None):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if role and session["user"]["role"] != role:
                abort(403)
            return fn(*args, **kwargs)
        return decorated
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def read_file_text(path):
    ext = path.rsplit(".", 1)[1].lower()
    try:
        if ext == "txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if ext == "pdf" and PyPDF2:
            text = []
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for p in reader.pages:
                    try:
                        t = p.extract_text() or ""
                        text.append(t)
                    except Exception:
                        continue
            return "\n".join(text)
        if ext == "docx" and docx:
            doc = docx.Document(path)
            return "\n".join([p.text for p in doc.paragraphs])
        if ext in ("csv","xlsx") and pd:
            if ext == "csv":
                df = pd.read_csv(path, dtype=str, encoding="utf-8", errors="ignore")
            else:
                df = pd.read_excel(path, dtype=str)
            rows = df.fillna("").astype(str).head(20)
            text = " | ".join(rows.columns.tolist()) + "\n"
            for _, r in rows.iterrows():
                text += " | ".join(r.tolist()) + "\n"
            return text
    except Exception:
        pass
    # fallback: attempt read raw
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:20000]
    except Exception:
        return ""

def firestore_get_docs():
    """Return list of (id, data) from Firestore collection 'docs' if available"""
    results = []
    if FS_CLIENT:
        try:
            coll = FS_CLIENT.collection("docs").stream()
            for doc in coll:
                d = doc.to_dict() or {}
                results.append((doc.id, d))
        except Exception:
            pass
    return results

def find_relevant_docs_local(question):
    q = question.lower()
    hits = []
    # First check Firestore
    if FS_CLIENT:
        try:
            docs = firestore_get_docs()
            for fn, info in docs:
                summary = (info.get("summary") or "").lower()
                content = (info.get("content") or "").lower()
                if q in summary or q in content:
                    hits.append((fn, info))
                else:
                    for token in q.split():
                        if token and (token in summary or token in content):
                            hits.append((fn, info)); break
        except Exception:
            pass
    # Then in-memory DOCS
    for fn, info in DOCS.items():
        summary = (info.get("summary") or "").lower()
        content = (info.get("content") or "").lower()
        if q in summary or q in content:
            hits.append((fn, info))
        else:
            for token in q.split():
                if token and (token in summary or token in content):
                    hits.append((fn, info)); break
    # keep unique by filename (prefer Firestore ids first)
    seen = set()
    uniq = []
    for fn, info in hits:
        if fn not in seen:
            seen.add(fn); uniq.append((fn, info))
    return uniq

def serpapi_search(query, num=3):
    """Perform SerpAPI search and return textual snippets (Vietnamese results if possible)."""
    if not SERPAPI_KEY:
        return ""
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "engine": "google",
        "api_key": SERPAPI_KEY,
        "num": num,
        "hl": "vi"
    }
    try:
        r = requests.get(url, params=params, timeout=8)
        if r.status_code == 200:
            data = r.json()
            snippets = []
            # organic_results
            for item in data.get("organic_results", [])[:num]:
                title = item.get("title") or ""
                snippet = item.get("snippet") or item.get("snippet_highlighted_words") or ""
                link = item.get("link") or ""
                snippets.append(f"{title}\n{snippet}\n{link}")
            return "\n\n".join(snippets)
    except Exception:
        pass
    return ""

def openai_summarize(text, max_tokens=400):
    if not OPENAI_AVAILABLE:
        return "(Không có OpenAI key để tóm tắt)"
    try:
        prompt = [
            {"role":"system","content":"Bạn là trợ lý tóm tắt tiếng Việt, tóm tắt rõ ràng, đủ ý."},
            {"role":"user","content":f"Hãy tóm tắt đoạn văn sau (tiếng Việt) trong 3-6 câu, nêu mục đích chính và các điểm quan trọng:\n\n{text}"}
        ]
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=prompt,
            max_tokens=max_tokens,
            temperature=0.2
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        return "(Không thể tóm tắt bằng OpenAI)"

def openai_answer(question, context_text="", max_tokens=500):
    if not OPENAI_AVAILABLE:
        return "AI (OpenAI) không được cấu hình."
    try:
        prompt = [
            {"role":"system","content":"Bạn là trợ lý tiếng Việt trả lời dựa trên nguồn được cung cấp. Nếu có nguồn, nêu rõ tên file hoặc link."},
            {"role":"user","content":f"Ngữ cảnh:\n{context_text}\n\nCâu hỏi: {question}\n\nTrả lời bằng tiếng Việt, rõ ràng, ngắn gọn, nêu nguồn nếu có."}
        ]
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=prompt,
            max_tokens=max_tokens,
            temperature=0.1
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        return "Lỗi khi gọi OpenAI."

# -------------------------
# Base template pieces (using Jinja - no f-strings with braces)
# -------------------------
BASE_HEADER = """
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Hệ Thống Chi Bộ</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { padding-bottom: 80px; }
    /* Chat popup */
    #chat-button { position: fixed; right: 24px; bottom: 24px; z-index: 2000; }
    #chat-popup { position: fixed; right: 24px; bottom: 80px; width: 360px; max-width: 90%; z-index: 2000; display: none; }
    #chat-messages { height: 300px; overflow:auto; background: #fff; }
    .chat-msg { margin-bottom:8px; }
    .from-user { text-align:right; }
    .from-bot { text-align:left; }
  </style>
</head>
<body>
<nav class="navbar navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <span class="navbar-brand">Hệ Thống Chi Bộ</span>
    <div class="text-white">
      {% if session.get('user') %}
        {{ session.get('user').get('name','') }} ({{ session.get('user').get('username') }})
        <a href="{{ url_for('logout') }}" class="btn btn-danger btn-sm ms-3">Đăng xuất</a>
      {% endif %}
    </div>
  </div>
</nav>
<div class="container">
"""

BASE_FOOTER = """
</div>

<!-- Chat popup button -->
<button id="chat-button" class="btn btn-info rounded-circle" title="Chatbot">
  💬
</button>

<!-- Chat popup -->
<div id="chat-popup" class="card shadow">
  <div class="card-header d-flex justify-content-between align-items-center">
    <div><strong>Chatbot - Tra cứu tài liệu</strong><br><small class="text-muted">Ưu tiên tài liệu nội bộ</small></div>
    <div>
      <button id="clear-history" class="btn btn-sm btn-outline-danger">Xóa lịch sử</button>
      <button id="close-chat" class="btn btn-sm btn-outline-secondary">×</button>
    </div>
  </div>
  <div class="card-body d-flex flex-column p-2">
    <div id="chat-messages" class="mb-2 p-2 border bg-light"></div>
    <form id="chat-form" class="d-flex" onsubmit="return false;">
      <input id="chat-input" class="form-control me-2" placeholder="Nhập câu hỏi..." />
      <button id="chat-submit" class="btn btn-primary">Hỏi</button>
    </form>
    <div id="chat-error" class="text-danger small mt-2" style="display:none;"></div>
  </div>
</div>

<script>
const btn = document.getElementById('chat-button');
const popup = document.getElementById('chat-popup');
const closeBtn = document.getElementById('close-chat');
const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');
const messages = document.getElementById('chat-messages');
const clearBtn = document.getElementById('clear-history');
const errorBox = document.getElementById('chat-error');

btn.addEventListener('click', () => {
  popup.style.display = 'block';
  input.focus();
});
closeBtn.addEventListener('click', () => { popup.style.display = 'none'; });

function appendMessage(text, from='bot') {
  const el = document.createElement('div');
  el.className = 'chat-msg ' + (from==='user' ? 'from-user' : 'from-bot');
  el.innerHTML = '<div class="small text-muted">' + (from==='user' ? 'Bạn' : 'Trợ lý') + '</div><div>' + text + '</div>';
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
}

async function askQuestion(q) {
  errorBox.style.display = 'none';
  appendMessage(q, 'user');
  appendMessage('Đang trả lời...', 'bot');
  try {
    const resp = await fetch('{{ url_for("chat_api") }}', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question: q})
    });
    const j = await resp.json();
    // remove the "Đang trả lời..." last bot message
    const last = messages.querySelectorAll('.from-bot');
    if (last.length) last[last.length-1].remove();
    if (j.error) {
      appendMessage('Lỗi: ' + j.error, 'bot');
    } else {
      appendMessage(j.answer.replace(/\\n/g,'<br/>'), 'bot');
    }
  } catch (e) {
    const last = messages.querySelectorAll('.from-bot');
    if (last.length) last[last.length-1].remove();
    appendMessage('Lỗi kết nối. Vui lòng thử lại.', 'bot');
  }
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = input.value && input.value.trim();
  if (!q) { errorBox.textContent = 'Vui lòng nhập câu hỏi.'; errorBox.style.display='block'; return; }
  input.value = '';
  await askQuestion(q);
});

clearBtn.addEventListener('click', async () => {
  if (!confirm('Xác nhận xóa lịch sử chat trên server cho user này?')) return;
  try {
    const resp = await fetch('{{ url_for("chat_clear_api") }}', {method:'POST'});
    const j = await resp.json();
    if (j.ok) {
      messages.innerHTML = '';
    } else {
      alert('Xóa không thành công.');
    }
  } catch (e) {
    alert('Lỗi kết nối.');
  }
});
</script>

</body>
</html>
"""

# -------------------------
# Routes (HTML embedded)
# -------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/static/<path:p>")
def static_file(p):
    return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), p)

# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","")
        if u in USERS and USERS[u]["password"] == p:
            # only demo account shown on page, but allow other accounts login (admin/bithu)
            session["user"] = {"username": u, "role": USERS[u]["role"], "name": USERS[u].get("name", u)}
            return redirect(url_for("dashboard"))
        else:
            err = "Sai tài khoản hoặc mật khẩu"
    # Login HTML (shows demo credentials note)
    html = """
<h3 class="text-center">Đăng nhập</h3>
<div class="row justify-content-center">
  <div class="col-md-5">
    <form method="post">
      <div class="mb-2">
        <label class="form-label">Tài khoản</label>
        <input class="form-control" name="username" required autofocus>
      </div>
      <div class="mb-2">
        <label class="form-label">Mật khẩu</label>
        <input class="form-control" type="password" name="password" required>
      </div>
      <button class="btn btn-primary w-100">Đăng nhập</button>
    </form>
    <p class="text-danger mt-2">{{ err }}</p>
    <div class="alert alert-secondary mt-3 small">
      <strong>Tài khoản DEMO:</strong><br>
      ID: <code>user_demo</code><br>
      Mật khẩu: <code>Test@123</code><br>
      <em>Chỉ dùng để thử nghiệm demo.</em>
    </div>
  </div>
</div>
"""
    full = BASE_HEADER + html + BASE_FOOTER
    return render_template_string(full, err=err)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["user"]["role"]
    if role == "admin":
        return redirect(url_for("admin"))
    if role == "bithu":
        return redirect(url_for("chi_bo"))
    return redirect(url_for("dang_vien"))

# Admin
@app.route("/admin")
@login_required("admin")
def admin():
    html = """
<h3>Quản trị hệ thống</h3>
<table class="table table-sm">
  <thead><tr><th>Tài khoản</th><th>Vai trò</th><th>Tên</th></tr></thead>
  <tbody>
    {% for u,info in users.items() %}
    <tr><td>{{u}}</td><td>{{info.role}}</td><td>{{info.name if info.name else ''}}</td></tr>
    {% endfor %}
  </tbody>
</table>
"""
    full = BASE_HEADER + html + BASE_FOOTER
    return render_template_string(full, users=USERS)

# Chi bộ (bí thư)
@app.route("/chi_bo", methods=["GET","POST"])
@login_required("bithu")
def chi_bo():
    msg_err = ""
    if request.method == "POST":
        # allow setting baso for chi bo and add sinh hoat
        baso = request.form.get("baso","").strip()
        noi = request.form.get("noi_dung","").strip()
        if baso:
            CHI_BO_INFO['baso'] = baso
        if noi:
            SINH_HOAT.append(noi)
    html = """
<h3>Trang Bí thư - Chi bộ</h3>

<form method="post" class="mb-3">
  <div class="mb-2">
    <label class="form-label">Mã/ba số (baso) của Chi bộ</label>
    <input class="form-control" name="baso" value="{{ chi_bo_info.get('baso','') }}">
  </div>
  <div class="mb-2">
    <label class="form-label">Thêm hoạt động chung</label>
    <textarea class="form-control" name="noi_dung"></textarea>
  </div>
  <button class="btn btn-success">Lưu / Thêm</button>
</form>

<h5>Hoạt động chung</h5>
<ul>
  {% for x in sinhhoat %}
    <li>{{x}}</li>
  {% else %}
    <li>Chưa có hoạt động.</li>
  {% endfor %}
</ul>

<h5 class="mt-4">Nhận xét Đảng viên (chọn để chỉnh)</h5>
<ul>
  {% for u,info in users.items() %}
    {% if info.role == 'dangvien' %}
      <li><a href="{{ url_for('nhan_xet', dv=u) }}">Nhận xét {{ u }}</a></li>
    {% endif %}
  {% endfor %}
</ul>
"""
    full = BASE_HEADER + html + BASE_FOOTER
    return render_template_string(full,
                                  sinhhoat=SINH_HOAT,
                                  users=USERS,
                                  chi_bo_info=CHI_BO_INFO,
                                  msg_err=msg_err)

@app.route("/nhan_xet/<dv>", methods=["GET","POST"])
@login_required("bithu")
def nhan_xet(dv):
    if dv not in USERS or USERS[dv]["role"] != "dangvien":
        abort(404)
    if request.method == "POST":
        ND = request.form.get("noidung","").strip()
        NHAN_XET[dv] = ND
    html = """
<h3>Nhận xét Đảng viên: {{ dv }}</h3>
<form method="post">
  <textarea class="form-control" name="noidung" required>{{ nhan_xet }}</textarea>
  <button class="btn btn-primary mt-3">Lưu nhận xét</button>
</form>
"""
    full = BASE_HEADER + html + BASE_FOOTER
    return render_template_string(full, dv=dv, nhan_xet=NHAN_XET.get(dv,""))

# Đảng viên
@app.route("/dang_vien")
@login_required("dangvien")
def dang_vien():
    dv = session["user"]["username"]
    html = """
<h3>Trang Đảng viên: {{ dv }}</h3>

<h5>Nhận xét của Bí thư</h5>
<div class="border p-2">{{ nx or "Chưa có nhận xét." }}</div>

<h5 class="mt-3">Hoạt động chung</h5>
<ul>
  {% for x in sinhhoat %}
    <li>{{ x }}</li>
  {% else %}
    <li>Chưa có hoạt động.</li>
  {% endfor %}
</ul>

<p class="small text-muted mt-3">Mã chi bộ: {{ chi_bo_info.get('baso','(chưa thiết lập)') }}</p>
"""
    full = BASE_HEADER + html + BASE_FOOTER
    return render_template_string(full,
                                  dv=dv,
                                  nx=NHAN_XET.get(dv),
                                  sinhhoat=SINH_HOAT,
                                  chi_bo_info=CHI_BO_INFO)

# Upload document (stores in Firestore if configured, else in-memory)
@app.route("/upload", methods=["GET","POST"])
@login_required()
def upload():
    err = ""
    if request.method == "POST":
        if "file" not in request.files:
            err = "Không có file!"
        else:
            f = request.files["file"]
            if f and allowed_file(f.filename):
                filename = secure_filename(f.filename)
                path = os.path.join(UPLOAD_FOLDER, filename)
                # avoid overwrite
                base, ext = os.path.splitext(filename)
                cnt = 1
                while os.path.exists(path):
                    filename = f"{base}_{cnt}{ext}"
                    path = os.path.join(UPLOAD_FOLDER, filename)
                    cnt += 1
                f.save(path)
                content = read_file_text(path)
                summary = openai_summarize(content[:6000]) if content else "(Không có nội dung trích xuất)"
                uploader = session["user"]["username"]
                # Save to Firestore if possible
                saved_to_fs = False
                if FS_CLIENT:
                    try:
                        FS_CLIENT.collection("docs").document(filename).set({
                            "summary": summary,
                            "content": content,
                            "uploader": uploader
                        })
                        saved_to_fs = True
                    except Exception:
                        saved_to_fs = False
                # Always keep in-memory as well
                DOCS[filename] = {"summary": summary, "content": content, "uploader": uploader}
                if not saved_to_fs:
                    # no success indicator (we do not show success flash), but page will display file list
                    pass
            else:
                err = "File không hợp lệ!"
    html = """
<h3>Upload tài liệu</h3>
<form method="post" enctype="multipart/form-data">
  <input type="file" name="file" class="form-control">
  <button class="btn btn-success mt-2">Tải lên</button>
</form>
<p class="text-danger mt-2">{{ err }}</p>

<h5 class="mt-4">Danh sách tài liệu (ưu tiên Firestore nếu có)</h5>
<table class="table table-sm">
  <thead><tr><th>File</th><th>Uploader</th><th>Tóm tắt</th><th>Hành động</th></tr></thead>
  <tbody>
    {% for fn,info in docs.items() %}
      <tr>
        <td>{{ fn }}</td>
        <td>{{ info.uploader }}</td>
        <td style="max-width:420px"><small>{{ info.summary }}</small></td>
        <td><a href="{{ url_for('doc_view', fn=fn) }}" class="btn btn-sm btn-outline-info">Xem</a></td>
      </tr>
    {% else %}
      <tr><td colspan="4">Chưa có tài liệu</td></tr>
    {% endfor %}
  </tbody>
</table>
"""
    # If Firestore docs exist, merge them into listing (Firestore prioritized)
    merged_docs = {}
    if FS_CLIENT:
        try:
            for doc_id, data in firestore_get_docs():
                merged_docs[doc_id] = {
                    "uploader": data.get("uploader","FS"),
                    "summary": data.get("summary",""),
                    "content": data.get("content","")
                }
        except Exception:
            pass
    # overlay in-memory DOCS for files not in Firestore
    for fn, info in DOCS.items():
        if fn not in merged_docs:
            merged_docs[fn] = info
    full = BASE_HEADER + html + BASE_FOOTER
    return render_template_string(full, err=err, docs=merged_docs)

@app.route("/docs/<fn>")
@login_required()
def doc_view(fn):
    # Try Firestore first
    info = None
    if FS_CLIENT:
        try:
            doc = FS_CLIENT.collection("docs").document(fn).get()
            if doc.exists:
                info = doc.to_dict()
                info.setdefault("uploader","(FS)")
        except Exception:
            info = None
    if not info:
        info = DOCS.get(fn)
    if not info:
        abort(404)
    html = """
<h3>{{ fn }}</h3>
<p><b>Người tải lên:</b> {{ info.uploader }}</p>
<h5>Tóm tắt</h5>
<div class="border p-2">{{ info.summary }}</div>

<h5 class="mt-3">Nội dung (trích)</h5>
<pre class="border p-2" style="white-space: pre-wrap;">{{ info.content[:2000] }}</pre>
"""
    full = BASE_HEADER + html + BASE_FOOTER
    return render_template_string(full, fn=fn, info=info)

# -------------------------
# Chat APIs (popup uses these endpoints)
# -------------------------
@app.route("/api/chat", methods=["POST"])
@login_required()
def chat_api():
    data = request.get_json() or {}
    q = data.get("question","").strip()
    user = session["user"]["username"]
    if not q:
        return {"error":"Vui lòng nhập câu hỏi"}, 400

    # 1) Tìm trong Firestore / nội bộ
    relevant = find_relevant_docs_local(q)
    context_parts = []
    if relevant:
        for fn, info in relevant[:5]:
            # include file name + summary
            summary = info.get("summary","")
            context_parts.append(f"File: {fn}\nTóm tắt: {summary}")
        context_text = "\n\n".join(context_parts)
        # Use OpenAI to answer using context
        answer = openai_answer(q, context_text=context_text) if OPENAI_AVAILABLE else \
                 ("Dựa trên tài liệu:\n" + ("\n".join([f"{fn}: {info.get('summary','')}" for fn,info in relevant])))
    else:
        # NOT FOUND IN INTERNAL DOCS -> do real web search via SerpAPI and synthesize with OpenAI
        # Per requirement: ABSOLUTELY no fake fallback. Use SerpAPI (real web) then OpenAI to synthesize.
        web_snippets = serpapi_search(q)
        if not web_snippets:
            answer = "Không tìm thấy thông tin trong tài liệu nội bộ và không thể truy vấn web tại thời điểm này."
        else:
            # synthesize with OpenAI
            if OPENAI_AVAILABLE:
                answer = openai_answer(q, context_text=web_snippets)
            else:
                answer = "Tài liệu nội bộ không có. Kết quả tìm kiếm web:\n\n" + web_snippets

    # Save chat history in Firestore if possible, else in-memory
    try:
        CHAT_HISTORY.setdefault(user, []).append({"question": q, "answer": answer})
        if FS_CLIENT:
            try:
                # append to a document per user
                doc_ref = FS_CLIENT.collection("chat_history").document(user)
                doc = doc_ref.get()
                if doc.exists:
                    old = doc.to_dict().get("items", [])
                    old.append({"question": q, "answer": answer})
                    doc_ref.set({"items": old})
                else:
                    doc_ref.set({"items": [{"question": q, "answer": answer}]})
            except Exception:
                pass
    except Exception:
        pass

    return {"answer": answer}

@app.route("/api/chat/clear", methods=["POST"])
@login_required()
def chat_clear_api():
    user = session["user"]["username"]
    CHAT_HISTORY[user] = []
    if FS_CLIENT:
        try:
            FS_CLIENT.collection("chat_history").document(user).set({"items":[]})
        except Exception:
            pass
    return {"ok": True}

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    # Port set by environment or default
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
