import os
import re
import requests
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    session, abort, send_from_directory, flash, get_flashed_messages, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Optional dependencies
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False

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

# SỬA LỖI 1: Cập nhật cách khởi tạo OpenAI Client (từ 0.x.x sang 1.x.x)
try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    # Khởi tạo client mới (Version 1.x)
    OPENAI_CLIENT = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    OPENAI_AVAILABLE = bool(OPENAI_CLIENT)
except Exception:
    openai = None
    OPENAI_CLIENT = None
    OPENAI_AVAILABLE = False

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-2025-change-in-production")
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}
LOGO_PATH = "/static/Logo.png"

# -------------------------
# Data storage
# -------------------------
USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Bí thư Chi bộ"},
    "user_demo": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "User Demo"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Đảng viên 01"},
}

DOCS = {}           # filename -> dict
CHAT_HISTORY = {}   # username -> list
NHAN_XET = {}       # dv_code -> text
SINH_HOAT = []      # list of activities
CHI_BO_INFO = {"name": "Chi bộ 1", "baso": ""}

FS_CLIENT = None
if FIRESTORE_AVAILABLE:
    try:
        FS_CLIENT = firestore.Client()
    except Exception:
        pass

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

def admin_required(fn):
    return login_required("admin")(fn)

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
                for page in reader.pages:
                    t = page.extract_text() or ""
                    text.append(t)
            return "\n".join(text)
        if ext == "docx" and docx:
            doc_obj = docx.Document(path)
            return "\n".join([p.text for p in doc_obj.paragraphs])
        if ext in ("csv", "xlsx") and pd:
            df = pd.read_csv(path) if ext == "csv" else pd.read_excel(path)
            return df.head(30).to_string()
    except Exception:
        pass
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:30000]
    except Exception:
        return ""
    return ""

def firestore_get(collection_name):
    if not FS_CLIENT: return []
    try:
        return [(d.id, d.to_dict()) for d in FS_CLIENT.collection(collection_name).stream()]
    except Exception:
        return []

# SỬA LỖI 2: Cập nhật hàm openai_summarize để dùng OPENAI_CLIENT
def openai_summarize(text):
    if not OPENAI_AVAILABLE or not text.strip():
        return "Không thể tóm tắt (thiếu OpenAI hoặc nội dung rỗng)."
    try:
        resp = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Tóm tắt tài liệu sau bằng tiếng Việt, 4-7 câu:\n\n{text[:6000]}"}],
            max_tokens=400,
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Lỗi tóm tắt bằng AI: {str(e)}"

# SỬA LỖI 3: Cập nhật hàm openai_answer để dùng OPENAI_CLIENT
def openai_answer(question, context=""):
    if not OPENAI_AVAILABLE:
        return "AI chưa được cấu hình. (Thiếu OPENAI_API_KEY)"
    try:
        messages = [
            # Thêm hướng dẫn RAG: CHỈ SỬ DỤNG thông tin ngữ cảnh để đảm bảo kết quả "thật"
            {"role": "system", "content": "Bạn là trợ lý Đảng viên. Trả lời chính xác, trang trọng bằng tiếng Việt. CHỈ SỬ DỤNG thông tin được cung cấp trong NGỮ CẢNH để trả lời, không giả định. Nếu không có thông tin, hãy nói không tìm thấy."},
            {"role": "user", "content": f"Ngữ cảnh:\n{context}\n\nCâu hỏi: {question}"}
        ]
        resp = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=600,
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Lỗi khi gọi AI: {str(e)}"

def serpapi_search(query, num=4):
    if not SERPAPI_KEY: return ""
    try:
        params = {"engine": "google", "q": query, "hl": "vi", "num": num, "api_key": SERPAPI_KEY}
        r = requests.get("https://serpapi.com/search", params=params, timeout=10)
        if r.status_code != 200: return ""
        data = r.json()
        snippets = []
        for item in data.get("organic_results", [])[:num]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            snippets.append(f"• {title}\n{snippet}\nNguồn: {link}")
        return "\n\n".join(snippets)
    except Exception:
        return ""

# -------------------------
# Templates (Cập nhật FOOTER để thêm nút Xóa lịch sử Chat)
# -------------------------
HEADER = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Hệ thống Quản lý Đảng viên</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        body {{ background: #f8fff8; padding-bottom: 100px; }}
        .navbar {{ background: #0f5132 !important; }}
        .footer {{ background: #0f5132; color: white; position: fixed; bottom: 0; width: 100%; padding: 12px 0; text-align: center; font-size: 0.9rem; }}
        #chat-button {{ position: fixed; right: 20px; bottom: 20px; z-index: 9999; width: 56px; height: 56px; border-radius: 50%; }}
        #chat-popup {{ position: fixed; right: 20px; bottom: 90px; width: 380px; max-width: 92vw; z-index: 9999; display: none; }}
    </style>
</head>
<body>
<nav class="navbar navbar-dark">
  <div class="container-fluid">
    <a class="navbar-brand" href="/dashboard">
      <img src="{LOGO_PATH}" alt="Logo" height="40" class="me-2">
      HỆ THỐNG QLNS - ĐẢNG VIÊN
    </a>
    {{% if session.user %}}
    <div class="text-white">
      <i class="bi bi-person-circle"></i> {{{{ session.user.name }}}} ({{{{ session.user.username }}}})
      <a href="{{{{ url_for('logout') }}}}" class="btn btn-outline-light btn-sm ms-3">Đăng xuất</a>
    </div>
    {{% endif %}}
  </div>
</nav>
<div class="container mt-4">
"""

FOOTER = """
</div>
<div class="footer">
    © 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu.
</div>

<button id="chat-button" class="btn btn-success shadow-lg fs-3"><i class="bi bi-chat-dots-fill"></i></button>
<div id="chat-popup" class="card shadow-lg">
  <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
    <strong>Trợ lý AI</strong>
    <button id="clear-chat" class="btn btn-sm btn-outline-light me-2">Xóa lịch sử</button>
    <button id="close-chat" class="btn-close btn-close-white"></button>
  </div>
  <div class="card-body p-2">
    <div id="chat-messages" class="border bg-light mb-2" style="height:320px; overflow-y:auto; padding:8px;"></div>
    <form id="chat-form" class="d-flex">
      <input id="chat-input" class="form-control form-control-sm me-1" placeholder="Hỏi về Điều lệ, Nghị quyết...">
      <button id="chat-submit" class="btn btn-success btn-sm">Gửi</button>
    </form>
  </div>
</div>

<script>
const popup = document.getElementById('chat-popup');
const chatMessages = document.getElementById('chat-messages');

document.getElementById('chat-button').onclick = () => popup.style.display = 'block';
document.getElementById('close-chat').onclick = () => popup.style.display = 'none';

// Thêm chức năng xóa lịch sử chat
document.getElementById('clear-chat').onclick = async () => {
    if (confirm("Bạn có chắc chắn muốn xóa lịch sử trò chuyện?")) {
        try {
            await fetch('/api/chat/clear', {method:'POST'});
            chatMessages.innerHTML = '';
            addMsg('Lịch sử trò chuyện đã được xóa.', 'bot', true);
        } catch(e) {
            alert('Lỗi khi xóa lịch sử.');
        }
    }
};

async function sendQuestion(q) {
  if (!q.trim()) return;
  document.getElementById('chat-input').value = '';
  addMsg(q, 'user');
  addMsg('Đang suy nghĩ...', 'bot');
  try {
    const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:q})});
    const j = await r.json();
    removeLastBot();
    addMsg((j.answer || j.error || 'Lỗi').replace(/\\n/g, '<br>'), 'bot');
  } catch(e) { removeLastBot(); addMsg('Lỗi kết nối', 'bot'); }
}
function addMsg(text, sender, isSystem=false) {
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (sender==='user'?'text-end':'');
  let senderName = sender === 'user' ? 'Bạn' : 'AI';
  let className = isSystem ? 'bg-warning text-dark' : (sender==='user'?'bg-primary text-white':'bg-light');
  
  div.innerHTML = `<small class="text-muted">${senderName}</small><div class="p-2 rounded ${className} d-inline-block">${text}</div>`;
  chatMessages.appendChild(div);
  div.scrollIntoView();
}
function removeLastBot() {
  const bots = chatMessages.querySelectorAll('.chat-msg:not(.text-end)');
  if (bots.length) bots[bots.length-1].remove();
}
document.getElementById('chat-form').onsubmit = e => { e.preventDefault(); sendQuestion(document.getElementById('chat-input').value); };
</script>
</body></html>
"""

# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = USERS.get(username)
        if user and check_password_hash(user["password"], password):
            session["user"] = {
                "username": username,
                "role": user["role"],
                "name": user.get("name", username)
            }
            return redirect(url_for("dashboard"))
        flash("Sai tài khoản hoặc mật khẩu", "danger")
    return render_template_string(HEADER + """
    <div class="row justify-content-center">
      <div class="col-md-4">
        <div class="card shadow">
          <div class="card-body">
            <h4 class="text-center mb-4">Đăng nhập hệ thống</h4>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
            {% endwith %}
            <form method="post">
              <div class="mb-3"><input class="form-control" name="username" placeholder="Tài khoản" required autofocus></div>
              <div class="mb-3"><input class="form-control" type="password" name="password" placeholder="Mật khẩu" required></div>
              <button class="btn btn-success w-100">Đăng nhập</button>
            </form>
            <div class="alert alert-info mt-3 small">
              <strong>Demo:</strong> user_demo / Test@123
            </div>
          </div>
        </div>
      </div>
    </div>
    """ + FOOTER)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["user"]["role"]
    if role == "admin": return redirect(url_for("admin_panel"))
    if role == "bithu": return redirect(url_for("chi_bo_panel"))
    return redirect(url_for("dangvien_panel"))

# ====================== ADMIN PANEL HOÀN CHỈNH ======================
@app.route("/admin")
@admin_required
def admin_panel():
    return render_template_string(HEADER + """
    <h3 class="text-success"><i class="bi bi-shield-lock"></i> Quản trị hệ thống</h3>
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h5>Danh sách người dùng</h5>
        <a href="{{url_for('admin_add_user')}}" class="btn btn-success"><i class="bi bi-plus-lg"></i> Thêm người dùng</a>
    </div>

    <table class="table table-bordered table-hover align-middle">
      <thead class="table-success">
        <tr><th>Tài khoản</th><th>Họ tên</th><th>Vai trò</th><th class="text-center">Hành động</th></tr>
      </thead>
      <tbody>
      {% for u,info in users.items() %}
        <tr>
          <td><strong>{{u}}</strong></td>
          <td>{{info.name}}</td>
          <td>{% if info.role=='admin' %}Quản trị viên{% elif info.role=='bithu' %}Bí thư Chi bộ{% else %}Đảng viên{% endif %}</td>
          <td class="text-center">
            <a href="{{url_for('admin_edit_user', username=u)}}" class="btn btn-sm btn-warning">Sửa</a>
            <a href="{{url_for('admin_reset_pass', username=u)}}" class="btn btn-sm btn-outline-danger"
               onclick="return confirm('Reset mật khẩu của {{u}} về Test@123?')">Reset MK</a>
            {% if u != 'admin' %}
            <a href="{{url_for('admin_delete_user', username=u)}}" class="btn btn-sm btn-danger"
               onclick="return confirm('XÓA HOÀN TOÀN tài khoản {{u}} ({{info.name}})? Không thể hoàn tác!')">Xóa</a>
            {% endif %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    """ + FOOTER, users=USERS)

@app.route("/admin/add", methods=["GET","POST"])
@admin_required
def admin_add_user():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        name = request.form["name"].strip()
        role = request.form["role"]
        if username in USERS:
            flash("Tài khoản đã tồn tại!", "danger")
        elif not username or not name:
            flash("Vui lòng nhập đầy đủ thông tin", "danger")
        else:
            USERS[username] = {
                "password": generate_password_hash("Test@123"),
                "role": role,
                "name": name
            }
            flash(f"Thêm thành công! Mật khẩu mặc định: Test@123", "success")
            return redirect(url_for("admin_panel"))
    return render_template_string(HEADER + """
    <h4>Thêm người dùng mới</h4>
    <form method="post" class="col-md-5">
      <div class="mb-3"><input name="username" class="form-control" placeholder="Tài khoản (vd: dv02)" required></div>
      <div class="mb-3"><input name="name" class="form-control" placeholder="Họ và tên" required></div>
      <div class="mb-3">
        <select name="role" class="form-select" required>
          <option value="dangvien">Đảng viên</option>
          <option value="bithu">Bí thư Chi bộ</option>
          <option value="admin">Quản trị viên</option>
        </select>
      </div>
      <button class="btn btn-success">Thêm người dùng</button>
      <a href="{{url_for('admin_panel')}}" class="btn btn-secondary ms-2">Quay lại</a>
    </form>
    """ + FOOTER)

@app.route("/admin/edit/<username>", methods=["GET","POST"])
@admin_required
def admin_edit_user(username):
    if username not in USERS:
        flash("Người dùng không tồn tại", "danger")
        return redirect(url_for("admin_panel"))
    if request.method == "POST":
        USERS[username]["name"] = request.form["name"].strip()
        USERS[username]["role"] = request.form["role"]
        flash("Cập nhật thành công!", "success")
        return redirect(url_for("admin_panel"))
    user = USERS[username]
    return render_template_string(HEADER + """
    <h4>Sửa thông tin: {{username}}</h4>
    <form method="post" class="col-md-5">
      <div class="mb-3"><input name="name" class="form-control" value="{{user.name}}" required></div>
      <div class="mb-3">
        <select name="role" class="form-select">
          <option value="dangvien" {% if user.role=='dangvien' %}selected{% endif %}>Đảng viên</option>
          <option value="bithu" {% if user.role=='bithu' %}selected{% endif %}>Bí thư Chi bộ</option>
          <option value="admin" {% if user.role=='admin' %}selected{% endif %}>Quản trị viên</option>
        </select>
      </div>
      <button class="btn btn-success">Lưu thay đổi</button>
      <a href="{{url_for('admin_panel')}}" class="btn btn-secondary ms-2">Hủy</a>
    </form>
    """ + FOOTER, username=username, user=user)

@app.route("/admin/reset/<username>")
@admin_required
def admin_reset_pass(username):
    if username in USERS:
        USERS[username]["password"] = generate_password_hash("Test@123")
        flash(f"Đã reset mật khẩu {username} về Test@123", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/delete/<username>")
@admin_required
def admin_delete_user(username):
    if username == "admin":
        flash("Không thể xóa tài khoản admin chính!", "danger")
    elif username in USERS:
        del USERS[username]
        NHAN_XET.pop(username, None)
        CHAT_HISTORY.pop(username, None)
        flash(f"Đã xóa hoàn toàn tài khoản {username}", "success")
    else:
        flash("Không tìm thấy người dùng", "danger")
    return redirect(url_for("admin_panel"))

# ====================== BÍ THƯ CHI BỘ ======================
@app.route("/chi-bo")
@login_required("bithu")
def chi_bo_panel():
    return render_template_string(HEADER + """
    <h3 class="text-success">Trang Bí thư Chi bộ</h3>
    <div class="row"><div class="col-md-7">
        <form method="post" action="{{url_for('chi_bo_update')}}">
          <div class="mb-3"><label class="form-label">Mã số Chi bộ (baso)</label>
            <input name="baso" class="form-control" value="{{chi_bo.baso or ''}}"></div>
          <div class="mb-3"><label class="form-label">Thêm hoạt động sinh hoạt chi bộ</label>
            <textarea name="hoatdong" class="form-control" rows="3"></textarea></div>
          <button class="btn btn-success">Lưu / Thêm hoạt động</button>
        </form>
      </div></div>
    <h5 class="mt-4">Hoạt động chi bộ</h5><ol>
      {% for a in sinhoat %}<li>{{a}}</li>{% else %}<li class="text-muted">Chưa có hoạt động</li>{% endfor %}
    </ol>
    <h5 class="mt-4">Nhận xét Đảng viên</h5>
    <div class="list-group">
      {% for u,info in users.items() if info.role == 'dangvien' %}
        <a href="{{url_for('nhanxet_edit', dv=u)}}" class="list-group-item list-group-item-action">{{info.name}} ({{u}})</a>
      {% else %}<p class="text-muted">Chưa có đảng viên nào.</p>{% endfor %}
    </div>
    """ + FOOTER, users=USERS, chi_bo=CHI_BO_INFO, sinhoat=SINH_HOAT)

@app.route("/chi-bo/update", methods=["POST"])
@login_required("bithu")
def chi_bo_update():
    baso = request.form.get("baso","").strip()
    hd = request.form.get("hoatdong","").strip()
    if baso: CHI_BO_INFO["baso"] = baso
    if hd: SINH_HOAT.append(f"[{datetime.now().strftime('%d/%m/%Y')}] {hd}")
    return redirect(url_for("chi_bo_panel"))

@app.route("/nhanxet/<dv>", methods=["GET","POST"])
@login_required("bithu")
def nhanxet_edit(dv):
    if dv not in USERS or USERS[dv]["role"] != "dangvien":
        abort(404)
    if request.method == "POST":
        NHAN_XET[dv] = request.form["noidung"]
        flash("Đã lưu nhận xét", "success")
    return render_template_string(HEADER + """
    <h4>Nhận xét Đảng viên: {{name}}</h4>
    <form method="post">
      <textarea name="noidung" class="form-control" rows="10">{{nhanxet}}</textarea>
      <button class="btn btn-success mt-3">Lưu nhận xét</button>
    </form>
    """ + FOOTER, name=USERS[dv]["name"], nhanxet=NHAN_XET.get(dv,""))

# ====================== ĐẢNG VIÊN ======================
@app.route("/dangvien")
@login_required("dangvien")
def dangvien_panel():
    dv = session["user"]["username"]
    return render_template_string(HEADER + """
    <h3>Xin chào Đảng viên <strong>{{name}}</strong></h3>
    <div class="row"><div class="col-md-8">
        <div class="card mb-3">
          <div class="card-header bg-success text-white">Nhận xét của Bí thư</div>
          <div class="card-body">{{nhanxet or "Chưa có nhận xét từ Bí thư."}}</div>
        </div>
        <div class="card mb-3">
          <div class="card-header bg-success text-white">Hoạt động chi bộ</div>
          <div class="card-body"><ol>
            {% for a in sinhoat %}<li>{{a}}</li>{% else %}<li>Chưa có hoạt động</li>{% endfor %}
          </ol></div>
        </div>
        <div class="card">
          <div class="card-header bg-success text-white">Thông tin chi bộ</div>
          <div class="card-body">
            <p><strong>Tên chi bộ:</strong> {{chi_bo.name}}</p>
            <p><strong>Mã số chi bộ:</strong> {{chi_bo.baso or "Chưa thiết lập"}}</p>
          </div>
        </div>
      </div></div>
    """ + FOOTER, name=session["user"]["name"], nhanxet=NHAN_XET.get(dv,"Chưa có nhận xét"),
        sinhoat=SINH_HOAT, chi_bo=CHI_BO_INFO)

# ====================== ĐỔI MẬT KHẨU ======================
@app.route("/change-password", methods=["GET","POST"])
@login_required()
def change_password():
    if request.method == "POST":
        old = request.form["old"]
        new1 = request.form["new1"]
        new2 = request.form["new2"]
        user = USERS[session["user"]["username"]]
        if not check_password_hash(user["password"], old):
            flash("Mật khẩu cũ không đúng", "danger")
        elif new1 != new2:
            flash("Mật khẩu mới không khớp", "danger")
        elif len(new1) < 8 or not re.search(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])", new1):
            flash("Mật khẩu phải ≥8 ký tự, có chữ hoa, thường, số và ký tự đặc biệt", "danger")
        else:
            USERS[session["user"]["username"]]["password"] = generate_password_hash(new1)
            flash("Đổi mật khẩu thành công!", "success")
            return redirect(url_for("dashboard"))
    return render_template_string(HEADER + """
    <h4>Đổi mật khẩu</h4>
    <form method="post" class="col-md-5">
      <div class="mb-3"><input type="password" name="old" class="form-control" placeholder="Mật khẩu cũ" required></div>
      <div class="mb-3"><input type="password" name="new1" class="form-control" placeholder="Mật khẩu mới" required></div>
      <div class="mb-3"><input type="password" name="new2" class="form-control" placeholder="Nhập lại mật khẩu mới" required></div>
      <button class="btn btn-success">Đổi mật khẩu</button>
    </form>
    """ + FOOTER)

# ====================== UPLOAD TÀI LIỆU ======================
@app.route("/upload", methods=["GET","POST"])
@login_required()
def upload():
    if request.method == "POST":
        if "file" not in request.files:
            flash("Chưa chọn file", "danger")
        else:
            file = request.files["file"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(path)
                content = read_file_text(path)
                summary = openai_summarize(content)
                uploader = session["user"]["username"]
                DOCS[filename] = {"content": content, "summary": summary, "uploader": uploader}
                if FS_CLIENT:
                    try:
                        FS_CLIENT.collection("docs").document(filename).set(DOCS[filename])
                    except: pass
                flash("Upload và tóm tắt thành công!", "success")
            else:
                flash("File không được phép", "danger")

    all_docs = DOCS.copy()
    if FS_CLIENT:
        for doc_id, data in firestore_get("docs"):
            all_docs[doc_id] = data

    return render_template_string(HEADER + """
    <h3>Upload tài liệu</h3>
    <form method="post" enctype="multipart/form-data" class="mb-4">
      <input type="file" name="file" class="form-control w-50 d-inline" required>
      <button class="btn btn-success ms-2">Tải lên</button>
    </form>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
    {% endwith %}
    <h5>Danh sách tài liệu</h5>
    <table class="table table-hover">
      <thead class="table-success"><tr><th>File</th><th>Tóm tắt</th><th>Uploader</th><th></th></tr></thead>
      {% for fn,info in docs.items() %}
      <tr>
        <td><strong>{{fn}}</strong></td>
        <td style="max-width:500px"><small>{{info.summary[:200]}}...</small></td>
        <td>{{info.uploader}}</td>
        <td><a href="{{url_for('doc_view', fn=fn)}}" class="btn btn-sm btn-outline-primary">Xem</a></td>
      </tr>
      {% else %}
      <tr><td colspan="4">Chưa có tài liệu</td></tr>
      {% endfor %}
    </table>
    <p><a href="{{url_for('change_password')}}" class="btn btn-outline-secondary">Đổi mật khẩu</a></p>
    """ + FOOTER, docs=all_docs)

@app.route("/doc/<fn>")
@login_required()
def doc_view(fn):
    info = DOCS.get(fn)
    if not info and FS_CLIENT:
        try:
            doc = FS_CLIENT.collection("docs").document(fn).get()
            if doc.exists: info = doc.to_dict()
        except: pass
    if not info: abort(404)
    return render_template_string(HEADER + """
    <h4>{{fn}}</h4>
    <p><strong>Người upload:</strong> {{info.uploader}}</p>
    <div class="card mb-3">
      <div class="card-header bg-success text-white">Tóm tắt AI</div>
      <div class="card-body">{{info.summary}}</div>
    </div>
    <div class="card">
      <div class="card-header">Nội dung (trích dẫn)</div>
      <div class="card-body"><pre style="max-height:600px; overflow:auto;">{{info.content[:5000]}}</pre></div>
    </div>
    """ + FOOTER, fn=fn, info=info)

# ====================== CHAT API ======================
@app.route("/api/chat", methods=["POST"])
@login_required()
def chat_api():
    data = request.get_json() or {}
    q = data.get("question","").strip()
    if not q:
        return {"error": "Câu hỏi rỗng"}, 400

    # Thêm thông tin Chi bộ vào ngữ cảnh
    chi_bo_context = f"""
    NGỮ CẢNH CHI BỘ:
    Tên chi bộ: {CHI_BO_INFO.get('name', 'N/A')}. 
    Mã số chi bộ (baso): {CHI_BO_INFO.get('baso', 'Chưa thiết lập')}.
    """
    context = chi_bo_context

    relevant = []
    q_lower = q.lower()
    # Tìm kiếm tài liệu liên quan trong DOCS
    for fn, info in DOCS.items():
        if q_lower in info.get("content","").lower() or q_lower in info.get("summary","").lower():
            relevant.append((fn, info))

    if relevant:
        # Ưu tiên sử dụng tài liệu đã upload (RAG)
        doc_context = "\n\n".join([f"Tài liệu: {fn}\nTóm tắt: {info['summary']}" for fn,info in relevant[:5]])
        context += "\n\nNGỮ CẢNH TÀI LIỆU:\n" + doc_context
        answer = openai_answer(q, context)
    else:
        # Nếu không có tài liệu liên quan, dùng tìm kiếm web
        web = serpapi_search(q)
        if web:
            context += "\n\nNGỮ CẢNH TÌM KIẾM WEB:\n" + web
        
        answer = openai_answer(q, context) if OPENAI_AVAILABLE else (web or "Không tìm thấy thông tin.")

    user = session["user"]["username"]
    CHAT_HISTORY.setdefault(user, []).append({"q": q, "a": answer, "time": datetime.now().isoformat()})
    return jsonify({"answer": answer})

# SỬA LỖI 4: Thêm API xóa lịch sử chat
@app.route("/api/chat/clear", methods=["POST"])
@login_required()
def chat_clear():
    user = session["user"]["username"]
    if user in CHAT_HISTORY:
        CHAT_HISTORY[user] = []
    return jsonify({"message": "Lịch sử chat đã được xóa"}), 200

# ====================== STATIC & RUN ======================
@app.route("/static/<path:p>")
def serve_static(p):
    return send_from_directory("static", p)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
