import os
import re
import unicodedata
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, render_template_string,
    session, abort, send_from_directory, flash, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ================== CONFIG ==================
app = Flask(__name__)
app.secret_key = "CHANGE_ME_SECRET"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}

# ================== MOCK DATABASE ==================
USERS = {
    "admin": {
        "password": generate_password_hash("Admin@123"),
        "role": "admin",
        "fullname": "Quản trị hệ thống"
    },
    "demo": {
        "password": generate_password_hash("Demo@123"),
        "role": "user",
        "fullname": "Người dùng demo"
    }
}

DOCS = {}          # filename -> info
CHAT_HISTORY = {}  # username -> messages


# ================== UTIL ==================
def allowed_file(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def normalize_filename(fn):
    fn = unicodedata.normalize("NFKD", fn).encode("ascii", "ignore").decode()
    fn = re.sub(r"[^\w.\-]", "_", fn)
    return fn


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if role and session["user"]["role"] != role:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def read_file_text(path):
    try:
        if path.lower().endswith(".txt"):
            return open(path, "r", encoding="utf-8", errors="ignore").read()
        return "[Không hỗ trợ xem trực tiếp định dạng này]"
    except:
        return "[Lỗi đọc file]"


def openai_answer(q):
    # MOCK – thay bằng OpenAI / Gemini / LLM thật nếu cần
    return f"🤖 AI trả lời: {q}"


# ================== TEMPLATE ==================
HEADER = """
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>HỆ THỐNG QLNS</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body{background:#e9f6ef}
.navbar{background:#0a6b4f}
.navbar a{color:white!important}
footer{background:#0a6b4f;color:#fff}
</style>
</head>
<body>
<nav class="navbar navbar-expand-lg">
  <div class="container-fluid">
    <a class="navbar-brand fw-bold" href="/">QLNS</a>
    <div class="ms-auto">
      {% if session.get("user") %}
        <span class="me-3">{{session["user"]["fullname"]}}</span>
        <a href="/change-password" class="btn btn-warning btn-sm">Đổi mật khẩu</a>
        <a href="/logout" class="btn btn-danger btn-sm ms-2">Logout</a>
      {% endif %}
    </div>
  </div>
</nav>
<div class="container my-4">
"""

FOOTER = """
</div>
<footer class="text-center py-2">© 2025 QLNS</footer>
</body>
</html>
"""


# ================== AUTH ==================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        user = USERS.get(u)
        if user and check_password_hash(user["password"], p):
            session["user"] = {
                "username": u,
                "role": user["role"],
                "fullname": user["fullname"]
            }
            return redirect(url_for("dashboard"))
        flash("Sai tài khoản hoặc mật khẩu", "danger")

    return render_template_string(HEADER + """
<h3>Đăng nhập</h3>
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}<div class="alert alert-danger">{{msgs[0][1]}}</div>{% endif %}
{% endwith %}
<form method="post" class="col-md-4">
  <input name="username" class="form-control mb-2" placeholder="Username">
  <input type="password" name="password" class="form-control mb-2" placeholder="Password">
  <button class="btn btn-success">Login</button>
</form>
""" + FOOTER)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================== DASHBOARD ==================
@app.route("/dashboard")
@login_required()
def dashboard():
    return render_template_string(HEADER + """
<h3>Dashboard</h3>

<a href="/upload" class="btn btn-primary mb-3">Upload tài liệu</a>
{% if session["user"]["role"] == "admin" %}
  <a href="/admin/users" class="btn btn-warning mb-3">Quản lý user</a>
{% endif %}

<h5>Danh sách tài liệu</h5>
<table class="table table-bordered bg-white">
<tr><th>Tên</th><th>Người upload</th><th>Thời gian</th><th></th></tr>
{% for k,v in docs.items() %}
<tr>
<td>{{k}}</td>
<td>{{v.user}}</td>
<td>{{v.uploaded_at}}</td>
<td><a href="/doc/{{k}}" class="btn btn-sm btn-success">Xem</a></td>
</tr>
{% endfor %}
</table>

<h5 class="mt-4">Chat AI</h5>
<textarea id="q" class="form-control"></textarea>
<button onclick="chat()" class="btn btn-success mt-2">Gửi</button>
<pre id="ans" class="mt-2"></pre>

<script>
function chat(){
 fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},
 body:JSON.stringify({question:document.getElementById("q").value})})
 .then(r=>r.json()).then(d=>document.getElementById("ans").innerText=d.answer)
}
</script>
""" + FOOTER, docs=DOCS)


# ================== UPLOAD ==================
@app.route("/upload", methods=["GET", "POST"])
@login_required()
def upload():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not allowed_file(f.filename):
            flash("File không hợp lệ", "danger")
        else:
            fn = normalize_filename(secure_filename(f.filename))
            path = os.path.join(UPLOAD_FOLDER, fn)
            f.save(path)
            DOCS[fn] = {
                "path": path,
                "user": session["user"]["username"],
                "uploaded_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "summary": "Tóm tắt AI tự động (demo)"
            }
            return redirect(url_for("dashboard"))

    return render_template_string(HEADER + """
<h4>Upload tài liệu</h4>
<form method="post" enctype="multipart/form-data">
  <input type="file" name="file" class="form-control mb-2">
  <button class="btn btn-success">Upload</button>
</form>
""" + FOOTER)


# ================== VIEW DOC ==================
@app.route("/doc/<fn>")
@login_required()
def doc_view(fn):
    if fn not in DOCS:
        abort(404)
    info = DOCS[fn]
    text = read_file_text(info["path"])[:15000]
    return render_template_string(HEADER + """
<h4>{{fn}}</h4>
<p>Upload bởi: {{info.user}} | {{info.uploaded_at}}</p>

<div class="card mb-3">
<div class="card-header bg-success text-white">Tóm tắt AI</div>
<div class="card-body">{{info.summary}}</div>
</div>

<pre class="bg-white p-3">{{text}}</pre>
<a href="/dashboard" class="btn btn-secondary">Quay lại</a>
""" + FOOTER, fn=fn, info=info, text=text)


# ================== CHANGE PASSWORD ==================
@app.route("/change-password", methods=["GET","POST"])
@login_required()
def change_password():
    u = session["user"]["username"]
    if request.method == "POST":
        if not check_password_hash(USERS[u]["password"], request.form["old"]):
            flash("Sai mật khẩu hiện tại", "danger")
        else:
            USERS[u]["password"] = generate_password_hash(request.form["new"])
            flash("Đổi mật khẩu thành công", "success")
            return redirect("/dashboard")
    return render_template_string(HEADER + """
<h4>Đổi mật khẩu</h4>
<form method="post" class="col-md-4">
<input type="password" name="old" class="form-control mb-2" placeholder="Mật khẩu cũ">
<input type="password" name="new" class="form-control mb-2" placeholder="Mật khẩu mới">
<button class="btn btn-success">Lưu</button>
</form>
""" + FOOTER)


# ================== ADMIN ==================
@app.route("/admin/users", methods=["GET","POST"])
@login_required("admin")
def admin_users():
    if request.method == "POST":
        u = request.form["username"]
        USERS[u] = {
            "password": generate_password_hash("Test@123"),
            "role": request.form["role"],
            "fullname": request.form["fullname"]
        }
    return render_template_string(HEADER + """
<h4>Quản lý User</h4>
<form method="post" class="row g-2">
<input name="username" placeholder="username" class="form-control col">
<input name="fullname" placeholder="Họ tên" class="form-control col">
<select name="role" class="form-control col">
<option value="user">User</option>
<option value="admin">Admin</option>
</select>
<button class="btn btn-success col-2">Thêm</button>
</form>

<table class="table mt-3 bg-white">
{% for u,v in users.items() %}
<tr><td>{{u}}</td><td>{{v.role}}</td></tr>
{% endfor %}
</table>
""" + FOOTER, users=USERS)


# ================== CHAT API ==================
@app.route("/api/chat", methods=["POST"])
@login_required()
def api_chat():
    q = request.json.get("question","")
    a = openai_answer(q)
    return jsonify({"answer":a})


# ================== MAIN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
