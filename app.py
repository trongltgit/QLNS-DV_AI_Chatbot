import os
import re
import unicodedata
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    session, abort, flash, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ====================== CẤU HÌNH ======================
app = Flask(__name__)
app.secret_key = "SECRET_KEY_CHANGE_ME"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ====================== DATA GIẢ ======================
USERS = {
    "admin": {
        "password": generate_password_hash("Admin@123"),
        "role": "admin",
        "name": "Quản trị"
    },
    "demo": {
        "password": generate_password_hash("Demo@123"),
        "role": "user",
        "name": "Demo User"
    }
}

CHI_BO = {
    "cb1": {"name": "Chi bộ 1"}
}

USER_CHIBO = {
    "demo": "cb1"
}

DOCS = {}

# ====================== HTML CHUNG ======================
HEADER = """
<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>QLNS Đảng viên</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-success text-white">
<nav class="navbar navbar-dark bg-success px-3">
  <span class="navbar-brand">HỆ THỐNG QLNS</span>
  {% if session.get('user') %}
  <span>{{session.user.username}} | 
    <a href="{{url_for('logout')}}" class="text-white">Đăng xuất</a>
  </span>
  {% endif %}
</nav>
<div class="container bg-white text-dark p-4 mt-3 rounded">
"""

FOOTER = """
</div>
<footer class="text-center text-white mt-4">
© 2025 QLNS
</footer>
</body></html>
"""

# ====================== HÀM PHỤ ======================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if role and session["user"]["role"] != role:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def read_file_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except:
        return ""

def openai_summarize(text):
    return "Tóm tắt tài liệu (demo AI)."

# ====================== LOGIN ======================
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        user = USERS.get(u)
        if user and check_password_hash(user["password"], p):
            session["user"] = {"username": u, "role": user["role"]}
            return redirect(url_for("dashboard"))
        flash("Sai đăng nhập", "danger")

    return render_template_string(HEADER + """
    <h4>Đăng nhập</h4>
    <form method="post" class="col-md-4">
      <input name="username" class="form-control mb-2" placeholder="User">
      <input name="password" type="password" class="form-control mb-2" placeholder="Password">
      <button class="btn btn-success">Login</button>
    </form>
    """ + FOOTER)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ====================== DASHBOARD ======================
@app.route("/dashboard")
@login_required()
def dashboard():
    return render_template_string(HEADER + """
    <h4>Dashboard</h4>
    <a href="{{url_for('upload')}}" class="btn btn-success mb-2">Upload tài liệu</a>
    <a href="{{url_for('change_password')}}" class="btn btn-secondary mb-2">Đổi mật khẩu</a>

    <hr>
    <h5>Tài liệu</h5>
    <ul>
    {% for k,v in docs.items() %}
      <li><a href="{{url_for('doc_view', fn=k)}}">{{k}}</a></li>
    {% endfor %}
    </ul>
    """ + FOOTER, docs=DOCS)

# ====================== UPLOAD ======================
@app.route("/upload", methods=["GET","POST"])
@login_required()
def upload():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not allowed_file(f.filename):
            flash("File không hợp lệ", "danger")
            return redirect(request.url)

        filename = secure_filename(f.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        f.save(path)

        text = read_file_text(path)
        summary = openai_summarize(text[:6000])

        DOCS[filename] = {
            "path": path,
            "uploaded_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "user": session["user"]["username"],
            "summary": summary
        }

        flash("Upload thành công", "success")
        return redirect(url_for("dashboard"))

    return render_template_string(HEADER + """
    <h4>Upload tài liệu</h4>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" class="form-control mb-2">
      <button class="btn btn-success">Upload</button>
    </form>
    """ + FOOTER)

# ====================== XEM DOC ======================
@app.route("/doc/<fn>")
@login_required()
def doc_view(fn):
    info = DOCS.get(fn)
    if not info:
        abort(404)

    content = read_file_text(info["path"])[:30000]

    return render_template_string(HEADER + """
    <h4>{{fn}}</h4>
    <p><b>Người upload:</b> {{info.user}}</p>
    <p><b>Thời gian:</b> {{info.uploaded_at}}</p>
    <div class="card mb-3">
      <div class="card-header bg-success text-white">Tóm tắt</div>
      <div class="card-body">{{info.summary}}</div>
    </div>
    <pre>{{content}}</pre>
    """ + FOOTER, fn=fn, info=info, content=content)

# ====================== ĐỔI PASS ======================
@app.route("/change-password", methods=["GET","POST"])
@login_required()
def change_password():
    u = session["user"]["username"]
    if request.method == "POST":
        old = request.form["old"]
        new = request.form["new"]
        if not check_password_hash(USERS[u]["password"], old):
            flash("Sai mật khẩu cũ", "danger")
        else:
            USERS[u]["password"] = generate_password_hash(new)
            flash("Đổi mật khẩu thành công", "success")
            return redirect(url_for("dashboard"))

    return render_template_string(HEADER + """
    <h4>Đổi mật khẩu</h4>
    <form method="post" class="col-md-4">
      <input type="password" name="old" class="form-control mb-2" placeholder="Mật khẩu cũ">
      <input type="password" name="new" class="form-control mb-2" placeholder="Mật khẩu mới">
      <button class="btn btn-success">Lưu</button>
    </form>
    """ + FOOTER)

# ====================== CHAT AI ======================
@app.route("/api/chat", methods=["POST"])
@login_required()
def api_chat():
    q = request.json.get("question","")
    return jsonify({"answer": f"AI trả lời: {q}"})

# ====================== RUN ======================
if __name__ == "__main__":
    app.run(debug=True)
