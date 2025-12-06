# app.py
import os
import secrets
from functools import wraps
from flask import (
    Flask, render_template_string, request, redirect, session,
    flash, send_from_directory, url_for, abort
)
from werkzeug.utils import secure_filename

# Optional libs for reading files
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
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
if OPENAI_KEY:
    try:
        import openai
        openai.api_key = OPENAI_KEY
    except Exception:
        openai = None
else:
    openai = None

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"pdf", "docx", "xlsx", "csv", "txt"}

# Fake DB (in-memory)
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "cb1": {"password": "Test@123", "role": "chi_bo", "name": "Chi bộ 1"},
    "dv1": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 1"},
    "user_demo": {"password": "Test@123", "role": "dang_vien", "name": "User Demo"},
}

DOCS = {}         # filename -> {"summary": str, "uploader": user, "content": str}
CHAT_HISTORY = {} # username -> [{"question":..., "answer":...}, ...]

# ---------- Utilities ----------
def login_required(role=None):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if role and session["user"]["role"] != role:
                flash("Bạn không có quyền truy cập!", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return decorated
    return wrapper

def render_page(content_html, title="HỆ THỐNG QLNS - ĐẢNG VIÊN"):
    # header shows user name and logout when logged in
    user_html = ""
    if "user" in session:
        u = session["user"]
        user_html = f'''
        <div class="ms-auto d-flex align-items-center">
          <div class="me-3 text-end">
            <div style="font-size:0.9rem">{u.get("name","")}</div>
            <div style="font-size:0.8rem;color:gray">{u.get("role","")}</div>
          </div>
          <a href="{url_for("logout")}" class="btn btn-outline-danger btn-sm">Đăng xuất</a>
        </div>
        '''
    page = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="d-flex flex-column min-vh-100">
  <header class="bg-light py-2 shadow-sm">
    <div class="container d-flex align-items-center">
      <img src="/static/Logo.png" alt="Logo" height="48" class="me-3">
      <h5 class="mb-0">{title}</h5>
      {user_html}
    </div>
  </header>
  <div class="container py-4 flex-fill">
    {content_html}
  </div>
  <footer class="bg-light text-center py-3 mt-auto">
    <div class="container">&copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu</div>
  </footer>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
    return page

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def read_file_text(filepath):
    """Try to extract plain text from common document types."""
    ext = filepath.rsplit(".",1)[1].lower()
    try:
        if ext == "pdf" and PyPDF2:
            text = []
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for p in reader.pages:
                    try:
                        text.append(p.extract_text() or "")
                    except Exception:
                        continue
            return "\n".join(text).strip()
        if ext == "docx" and docx:
            doc = docx.Document(filepath)
            return "\n".join([p.text for p in doc.paragraphs]).strip()
        if ext in {"csv","xlsx","txt"} and pd:
            if ext == "csv" or ext == "txt":
                df = pd.read_csv(filepath, dtype=str, encoding="utf-8", errors="ignore")
            else:
                df = pd.read_excel(filepath, dtype=str)
            # convert to simple text: header + first few rows
            rows = df.fillna("").astype(str).head(20)
            text = " | ".join(rows.columns.tolist()) + "\n"
            for _, r in rows.iterrows():
                text += " | ".join(r.tolist()) + "\n"
            return text
    except Exception:
        pass
    # fallback: read raw bytes as text
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:20000]
    except Exception:
        return ""

def call_openai_summary(text, max_tokens=400):
    """Call OpenAI to summarize text. Returns summary string or raises."""
    if not openai:
        raise RuntimeError("OpenAI SDK not available or OPENAI_API_KEY not set.")
    # keep prompt short & in Vietnamese
    system = "Bạn là một trợ lý tóm tắt tài liệu bằng tiếng Việt. Tóm tắt ngắn gọn những điểm chính, mục đích, và những dữ liệu/ghi chú quan trọng."
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Hãy tóm tắt văn bản dưới đây (nói tiếng Việt). Giữ trong 3-6 câu, nêu mục đích chính và các điểm đáng chú ý.\n\n---\n{text}"}
    ]
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini" if hasattr(openai, "ChatCompletion") else "gpt-4o",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        # response content
        content = ""
        if resp and "choices" in resp and len(resp["choices"])>0:
            content = resp["choices"][0]["message"]["content"].strip()
        return content
    except Exception as e:
        raise

def safe_summarize(text, filename="<file>"):
    """Try to summarize via OpenAI; fallback to simple heuristic summary."""
    try:
        if openai:
            s = call_openai_summary(text)
            if s:
                return s
    except Exception:
        pass
    # fallback simple summary
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return f"Tệp {filename} không có nội dung trích xuất được."
    # take first few lines as 'summary'
    top = " ".join(lines[:5])
    if len(top) > 600:
        top = top[:600] + "..."
    return f"Tóm tắt (fallback): {top}"

def find_relevant_docs(question):
    """Find docs whose summary or content contains keywords from question."""
    q = question.lower()
    results = []
    for fn,info in DOCS.items():
        # check summary and content
        if q in (info.get("summary","").lower()) or q in (info.get("content","").lower()):
            results.append((fn, info))
        else:
            # simple keyword match
            for token in q.split():
                if token and (token in info.get("summary","").lower() or token in info.get("content","").lower()):
                    results.append((fn, info)); break
    return results

def call_openai_answer(question, context_text="", max_tokens=400):
    if not openai:
        raise RuntimeError("OpenAI SDK not available or OPENAI_API_KEY not set.")
    system = "Bạn là trợ lý chuyên trả lời câu hỏi dựa trên tài liệu cung cấp (tiếng Việt). Nếu tài liệu không chứa câu trả lời, hãy trả lời ngắn gọn và rõ ràng."
    user_prompt = f"Context:\n{context_text}\n\nCâu hỏi: {question}\n\nHãy trả lời bằng tiếng Việt, rõ ràng, ngắn gọn, nêu nguồn nếu có (tên file)."
    messages = [
        {"role":"system","content":system},
        {"role":"user","content":user_prompt}
    ]
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini" if hasattr(openai, "ChatCompletion") else "gpt-4o",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        if resp and "choices" in resp and len(resp["choices"])>0:
            return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    raise RuntimeError("OpenAI request failed.")

# ---------- Routes ----------
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/static/<path:p>")
def static_file(p):
    # serve static Logo if exists under ./static
    return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), p)

# ----- LOGIN/LOGOUT -----
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        pw = request.form.get("password","")
        if username in USERS and USERS[username]["password"] == pw:
            session["user"] = {
                "username": username,
                "role": USERS[username]["role"],
                "name": USERS[username]["name"]
            }
            role = USERS[username]["role"]
            flash("Đăng nhập thành công", "success")
            if role == "admin":
                return redirect(url_for("admin_home"))
            if role == "chi_bo":
                return redirect(url_for("chi_bo_home"))
            return redirect(url_for("dang_vien_home"))
        flash("Sai tài khoản hoặc mật khẩu!", "danger")
    login_html = """
    <div class="card p-4 shadow mx-auto" style="max-width:480px;">
      <h3 class="text-center mb-3 text-success">Đăng nhập hệ thống</h3>
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}{% for cat,msg in messages %}
          <div class="alert alert-{{cat}} alert-dismissible fade show">{{msg}}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
        {% endfor %}{% endif %}
      {% endwith %}
      <form method="post" autocomplete="on">
        <label class="form-label">Tài khoản</label>
        <input type="text" class="form-control" name="username" required autofocus>
        <label class="form-label mt-3">Mật khẩu</label>
        <input type="password" class="form-control" name="password" required>
        <button class="btn btn-success w-100 mt-4">Đăng nhập</button>
      </form>
    </div>
    """
    return render_template_string(render_page(login_html, title="Đăng nhập"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Bạn đã đăng xuất.", "info")
    return redirect(url_for("login"))

# ----- DASHBOARD -----
@app.route("/dashboard")
@login_required()
def dashboard():
    u = session["user"]
    html = f"""
    <h3>Xin chào, {u.get('name')}</h3>
    <p>Role: {u.get('role')}</p>
    <a href="{url_for('logout')}" class="btn btn-danger mt-3">Đăng xuất</a>
    """
    return render_template_string(render_page(html))

# ----- ADMIN -----
@app.route("/admin")
@login_required("admin")
def admin_home():
    return redirect(url_for("admin_users"))

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    html = """
    <h3>Quản lý người dùng</h3>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}{% for cat,msg in messages %}
        <div class="alert alert-{{cat}} alert-dismissible fade show">{{msg}}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
      {% endfor %}{% endif %}
    {% endwith %}
    <table class="table table-striped mt-3">
      <thead><tr><th>ID</th><th>Tên</th><th>Role</th><th>Hành động</th></tr></thead>
      <tbody>
      {% for username,u in users.items() %}
        <tr>
          <td>{{username}}</td>
          <td>{{u.name}}</td>
          <td>{{u.role}}</td>
          <td>
            {% if username != "admin" and username!="user_demo" %}
              <a href="{{ url_for('admin_reset_user', username=username) }}" class="btn btn-sm btn-warning">Reset Pass</a>
            {% endif %}
            <a href="{{ url_for('admin_delete_user', username=username) }}" class="btn btn-sm btn-danger">Xóa</a>
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    """
    return render_template_string(render_page(html), users=USERS)

@app.route("/admin/users/delete/<username>")
@login_required("admin")
def admin_delete_user(username):
    if username in USERS and username not in ["admin", "user_demo"]:
        del USERS[username]
        flash("Đã xóa user", "success")
    else:
        flash("Không thể xóa user đặc biệt", "danger")
    return redirect(url_for("admin_users"))

@app.route("/admin/reset/<username>")
@login_required("admin")
def admin_reset_user(username):
    if username in USERS and username not in ["admin", "user_demo"]:
        USERS[username]["password"] = "Test@123"
        flash(f"Đã reset mật khẩu user {username} về Test@123", "success")
    else:
        flash("Không thể reset user đặc biệt", "danger")
    return redirect(url_for("admin_users"))

# ----- CHI BỘ -----
SINH_HOAT = {}  # chi_bo -> list of {title, content}

@app.route("/chi_bo")
@login_required("chi_bo")
def chi_bo_home():
    cb = session["user"]["username"]
    sinh_hoat = SINH_HOAT.get(cb, [])
    html = """
    <h3>Xin chào, {{session.user.name}} (Chi bộ)</h3>
    <h5>Thông báo sinh hoạt đảng</h5>
    <ul>
      {% for s in sinh_hoat %}
        <li><strong>{{s.title}}</strong>: {{s.content}}</li>
      {% else %}
        <li>Chưa có thông báo.</li>
      {% endfor %}
    </ul>
    <a href="{{ url_for('chi_bo_add') }}" class="btn btn-primary mt-2">Thêm thông báo/hoạt động</a>
    <a href="{{ url_for('logout') }}" class="btn btn-danger mt-2">Đăng xuất</a>
    """
    return render_template_string(render_page(html), sinh_hoat=sinh_hoat)

@app.route("/chi_bo/add", methods=["GET", "POST"])
@login_required("chi_bo")
def chi_bo_add():
    cb = session["user"]["username"]
    if request.method == "POST":
        title = request.form.get("title","").strip()
        content = request.form.get("content","").strip()
        if title and content:
            SINH_HOAT.setdefault(cb, []).append({"title": title, "content": content})
            flash("Đã thêm thông báo/hoạt động", "success")
            return redirect(url_for("chi_bo_home"))
        flash("Vui lòng nhập đủ tiêu đề và nội dung", "warning")
    html = """
    <h3>Thêm thông báo/hoạt động</h3>
    <form method="post">
      <label class="form-label">Tiêu đề</label><input class="form-control" name="title" required>
      <label class="form-label mt-2">Nội dung</label><textarea class="form-control" name="content" required></textarea>
      <button class="btn btn-success mt-3">Thêm</button>
    </form>
    <a href="{{ url_for('chi_bo_home') }}" class="btn btn-secondary mt-3">Quay lại</a>
    """
    return render_template_string(render_page(html))

# ----- ĐẢNG VIÊN -----
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    html = """
    <h3>Xin chào, {{ session.user.name }} (Đảng viên)</h3>
    <h5>Hoạt động cá nhân và liên quan</h5>
    <ul>
      {% for cb,slist in sinh_hoat.items() %}
        {% for s in slist %}
          <li><strong>{{s.title}}</strong>: {{s.content}}</li>
        {% endfor %}
      {% endfor %}
      {% if not sinh_hoat %}
        <li>Chưa có thông báo.</li>
      {% endif %}
    </ul>
    <a href="{{ url_for('upload_file') }}" class="btn btn-primary mt-2">Upload tài liệu</a>
    <a href="{{ url_for('chatbot') }}" class="btn btn-info mt-2">Chatbot tra cứu tài liệu</a>
    <a href="{{ url_for('logout') }}" class="btn btn-danger mt-2">Đăng xuất</a>
    """
    return render_template_string(render_page(html), sinh_hoat=SINH_HOAT)

# ----- UPLOAD TÀI LIỆU -----
@app.route("/dang_vien/upload", methods=["GET", "POST"])
@login_required("dang_vien")
def upload_file():
    username = session["user"]["username"]
    if request.method == "POST":
        f = request.files.get("file")
        if not f or f.filename == "":
            flash("Vui lòng chọn file để upload", "warning")
            return redirect(url_for("upload_file"))
        filename = secure_filename(f.filename)
        if not allowed_file(filename):
            flash("File không hợp lệ (cho phép: pdf, docx, xlsx, csv, txt)", "danger")
            return redirect(url_for("upload_file"))
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        # if filename exists, add suffix to avoid overwrite
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(save_path):
            filename = f"{base}_{counter}{ext}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            counter += 1
        f.save(save_path)
        # extract text
        content = read_file_text(save_path)
        # summarize via OpenAI (or fallback)
        try:
            summary = safe_summarize(content, filename=filename)
        except Exception:
            summary = f"Tóm tắt không thể tạo (lỗi hệ thống)."
        DOCS[filename] = {"summary": summary, "uploader": username, "content": content}
        flash("Upload thành công và đã tóm tắt nội dung (nếu có OpenAI).", "success")
        return redirect(url_for("upload_file"))
    # GET: show upload form and list
    html = """
    <h3>Upload tài liệu</h3>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}{% for cat,msg in messages %}
        <div class="alert alert-{{cat}} alert-dismissible fade show">{{msg}}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
      {% endfor %}{% endif %}
    {% endwith %}
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" class="form-control" required>
      <button class="btn btn-success mt-2">Upload</button>
    </form>
    <h5 class="mt-3">Danh sách tài liệu</h5>
    <table class="table table-sm">
      <thead><tr><th>File</th><th>Uploader</th><th>Tóm tắt</th><th>Hành động</th></tr></thead>
      <tbody>
      {% for fname, info in docs.items() %}
        <tr>
          <td>{{fname}}</td>
          <td>{{info.uploader}}</td>
          <td style="max-width:480px"><small>{{info.summary}}</small></td>
          <td>
            <a href="{{ url_for('download_file', filename=fname) }}" class="btn btn-sm btn-outline-primary">Tải</a>
            <a href="{{ url_for('view_doc', filename=fname) }}" class="btn btn-sm btn-outline-info">Xem</a>
            <a href="{{ url_for('delete_doc', filename=fname) }}" class="btn btn-sm btn-outline-danger">Xóa</a>
          </td>
        </tr>
      {% else %}
        <tr><td colspan="4">Chưa có tài liệu</td></tr>
      {% endfor %}
      </tbody>
    </table>
    <a href="{{ url_for('dang_vien_home') }}" class="btn btn-secondary mt-3">Quay lại</a>
    """
    return render_template_string(render_page(html), docs=DOCS)

@app.route("/uploads/<path:filename>")
@login_required()
def download_file(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/doc/view/<path:filename>")
@login_required()
def view_doc(filename):
    info = DOCS.get(filename)
    if not info:
        flash("Không tìm thấy tài liệu.", "danger")
        return redirect(url_for("upload_file"))
    html = f"""
    <h3>Chi tiết file: {filename}</h3>
    <p><strong>Uploader:</strong> {info.get('uploader')}</p>
    <h5>Tóm tắt</h5>
    <div class="border p-3 mb-3"><pre style="white-space:pre-wrap">{info.get('summary')}</pre></div>
    <h5>Nội dung (trích dẫn - giới hạn)</h5>
    <div class="border p-3"><pre style="white-space:pre-wrap; max-height:360px; overflow:auto">{(info.get('content') or '')[:5000]}</pre></div>
    <a href="{url_for('upload_file')}" class="btn btn-secondary mt-3">Quay lại</a>
    """
    return render_template_string(render_page(html))

@app.route("/doc/delete/<path:filename>")
@login_required()
def delete_doc(filename):
    if filename in DOCS:
        # delete file from disk
        path = os.path.join(UPLOAD_FOLDER, filename)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        del DOCS[filename]
        flash("Đã xóa tài liệu.", "success")
    else:
        flash("Không tìm thấy tài liệu.", "danger")
    return redirect(url_for("upload_file"))

# ----- CHATBOT -----
@app.route("/dang_vien/chatbot", methods=["GET", "POST"])
@login_required("dang_vien")
def chatbot():
    username = session["user"]["username"]
    CHAT_HISTORY.setdefault(username, [])
    answer = ""
    question = ""
    if request.method == "POST":
        question = request.form.get("question","").strip()
        if question:
            # find relevant docs
            relevant = find_relevant_docs(question)
            context_parts = []
            if relevant:
                for fn,info in relevant:
                    context_parts.append(f"File: {fn}\nSummary: {info.get('summary')}\n")
            else:
                # if none matched, include top-N summaries as possible context
                top = list(DOCS.items())[:3]
                for fn,info in top:
                    context_parts.append(f"File: {fn}\nSummary: {info.get('summary')}\n")
            context_text = "\n\n".join(context_parts) or "Không có nội dung tài liệu phù hợp."
            # call OpenAI to answer using context
            try:
                ans = call_openai_answer(question, context_text=context_text)
            except Exception:
                # fallback: simple rule-based answer
                if relevant:
                    first = relevant[0][1]
                    ans = f"Dựa trên tài liệu '{relevant[0][0]}': {first.get('summary')}"
                else:
                    ans = "Không tìm thấy thông tin liên quan trong tài liệu upload (vui lòng kiểm tra từ khóa hoặc upload thêm tài liệu)."
            CHAT_HISTORY[username].append({"question": question, "answer": ans})
            answer = ans
        else:
            flash("Vui lòng nhập câu hỏi.", "warning")
    html = """
    <h3>Chatbot tra cứu tài liệu</h3>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}{% for cat,msg in messages %}
        <div class="alert alert-{{cat}} alert-dismissible fade show">{{msg}}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
      {% endfor %}{% endif %}
    {% endwith %}
    <form method="post">
      <input class="form-control" name="question" placeholder="Nhập câu hỏi..." required value="{{ request.form.get('question','') }}">
      <button class="btn btn-info mt-2">Hỏi</button>
      <a href="{{ url_for('chatbot_clear') }}" class="btn btn-sm btn-danger mt-2 ms-2" onclick="return confirm('Xác nhận xóa lịch sử?')">Xóa lịch sử</a>
    </form>
    <h5 class="mt-3">Lịch sử hỏi đáp</h5>
    <ul>
      {% for q in history|reverse %}
        <li class="mb-2">
          <strong>Câu hỏi:</strong> {{q.question}} <br>
          <strong>Trả lời:</strong> <div class="border p-2"><pre style="white-space:pre-wrap">{{q.answer}}</pre></div>
        </li>
      {% else %}
        <li>Chưa có lịch sử hỏi đáp.</li>
      {% endfor %}
    </ul>
    <a href="{{ url_for('dang_vien_home') }}" class="btn btn-secondary mt-3">Quay lại</a>
    """
    return render_template_string(render_page(html), history=CHAT_HISTORY[username])

@app.route("/dang_vien/chatbot/clear")
@login_required("dang_vien")
def chatbot_clear():
    username = session["user"]["username"]
    CHAT_HISTORY[username] = []
    flash("Đã xóa lịch sử hỏi đáp.", "success")
    return redirect(url_for("chatbot"))

# ---------- Run ----------
if __name__ == "__main__":
    # Development server
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
