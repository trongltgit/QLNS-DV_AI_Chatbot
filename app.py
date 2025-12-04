from flask import Flask, render_template_string, request, redirect, session, flash, send_from_directory
from functools import wraps
import os
import secrets

app = Flask(__name__)

# SECRET KEY
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# =============================
# FAKE DATABASE
# =============================
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "cb1": {"password": "Test@123", "role": "chi_bo", "name": "Chi bộ 1"},
    "dv1": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 1"},
    "user_demo": {"password": "Test@123", "role": "dang_vien", "name": "User Demo"},
}

# =============================
# SESSION DATA
# =============================
DOCS = {}  # {filename: {"summary": "tóm tắt", "uploader": username}}
CHAT_HISTORY = {}  # {username: [{"question":"", "answer":""}, ...]}
SINH_HOAT = {}  # {chi_bo: [{"title": "...", "content": "..."}]}

# Upload folder
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =============================
# LOGIN REQUIRED DECORATOR
# =============================
def login_required(role=None):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect("/login")
            if role and session["user"]["role"] != role:
                flash("Bạn không có quyền truy cập!", "danger")
                return redirect("/dashboard")
            return fn(*args, **kwargs)
        return decorated
    return wrapper

# =============================
# COMMON HEADER & FOOTER
# =============================
def render_page(content_html, title="HỆ THỐNG QLNS - ĐẢNG VIÊN"):
    page = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{title}</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="d-flex flex-column min-vh-100">
      <header class="bg-light py-3 shadow">
        <div class="container d-flex align-items-center">
          <img src="/static/Logo.png" alt="Logo" height="50" class="me-3">
          <h4 class="mb-0">{title}</h4>
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

# =============================
# ROUTES
# =============================
@app.route("/")
def index():
    return redirect("/login")

# ----- LOGIN -----
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username = request.form.get("username")
        pw = request.form.get("password")
        if username in USERS and USERS[username]["password"]==pw:
            session["user"] = {"username": username, "role": USERS[username]["role"], "name": USERS[username]["name"]}
            role = USERS[username]["role"]
            if role=="admin":
                return redirect("/admin")
            elif role=="chi_bo":
                return redirect("/chi_bo")
            else:
                return redirect("/dang_vien")
        flash("Sai tài khoản hoặc mật khẩu!","danger")
    login_html="""
    <div class="card p-4 shadow mx-auto" style="max-width:400px;">
      <h3 class="text-center mb-3 text-success">Đăng nhập hệ thống</h3>
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}{% for cat,msg in messages %}
          <div class="alert alert-{{cat}} alert-dismissible fade show">{{msg}}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
        {% endfor %}{% endif %}
      {% endwith %}
      <form method="post">
        <label class="form-label">Tài khoản</label>
        <input type="text" class="form-control" name="username" required>
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
    return redirect("/login")

# ----- DASHBOARD -----
@app.route("/dashboard")
@login_required()
def dashboard():
    html=f"""
    <h3>Xin chào, {{ session.user.name }}</h3>
    <p>Role: {{ session.user.role }}</p>
    <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
    """
    return render_template_string(render_page(html))

# =============================
# ADMIN
# =============================
@app.route("/admin")
@login_required("admin")
def admin_home():
    return redirect("/admin/users")

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    html="""
    <h3>Quản lý người dùng</h3>
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
              <a href="/admin/reset/{{username}}" class="btn btn-sm btn-warning">Reset Pass</a>
            {% endif %}
            <a href="/admin/users/delete/{{username}}" class="btn btn-sm btn-danger">Xóa</a>
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
    if username in USERS and username not in ["admin","user_demo"]:
        del USERS[username]
        flash("Đã xóa user","success")
    else:
        flash("Không thể xóa user đặc biệt","danger")
    return redirect("/admin/users")

@app.route("/admin/reset/<username>")
@login_required("admin")
def admin_reset_user(username):
    if username in USERS and username not in ["admin","user_demo"]:
        USERS[username]["password"]="Test@123"
        flash(f"Đã reset mật khẩu user {username} về Test@123","success")
    else:
        flash("Không thể reset user đặc biệt","danger")
    return redirect("/admin/users")

# =============================
# CHI BỘ
# =============================
@app.route("/chi_bo")
@login_required("chi_bo")
def chi_bo_home():
    cb = session["user"]["username"]
    sinh_hoat = SINH_HOAT.get(cb,[])
    html="""
    <h3>Xin chào, {{ session.user.name }} (Chi bộ)</h3>
    <h5>Thông báo sinh hoạt đảng</h5>
    <ul>
      {% for s in sinh_hoat %}<li><strong>{{s.title}}</strong>: {{s.content}}</li>{% endfor %}
    </ul>
    <a href="/chi_bo/add" class="btn btn-primary mt-2">Thêm thông báo/hoạt động</a>
    <a href="/logout" class="btn btn-danger mt-2">Đăng xuất</a>
    """
    return render_template_string(render_page(html), sinh_hoat=sinh_hoat)

@app.route("/chi_bo/add", methods=["GET","POST"])
@login_required("chi_bo")
def chi_bo_add():
    cb = session["user"]["username"]
    if request.method=="POST":
        title = request.form.get("title")
        content = request.form.get("content")
        SINH_HOAT.setdefault(cb,[]).append({"title":title,"content":content})
        flash("Đã thêm thông báo/hoạt động","success")
        return redirect("/chi_bo")
    html="""
    <h3>Thêm thông báo/hoạt động</h3>
    <form method="post">
      <label class="form-label">Tiêu đề</label><input class="form-control" name="title" required>
      <label class="form-label mt-2">Nội dung</label><textarea class="form-control" name="content" required></textarea>
      <button class="btn btn-success mt-3">Thêm</button>
    </form>
    <a href="/chi_bo" class="btn btn-secondary mt-3">Quay lại</a>
    """
    return render_template_string(render_page(html))

# =============================
# ĐẢNG VIÊN
# =============================
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    username = session["user"]["username"]
    html="""
    <h3>Xin chào, {{ session.user.name }} (Đảng viên)</h3>
    <h5>Hoạt động cá nhân và liên quan</h5>
    <ul>
      {% for cb,slist in sinh_hoat.items() %}
        {% for s in slist %}
          <li><strong>{{s.title}}</strong>: {{s.content}}</li>
        {% endfor %}
      {% endfor %}
    </ul>
    <a href="/dang_vien/upload" class="btn btn-primary mt-2">Upload tài liệu</a>
    <a href="/dang_vien/chatbot" class="btn btn-info mt-2">Chatbot tra cứu tài liệu</a>
    <a href="/logout" class="btn btn-danger mt-2">Đăng xuất</a>
    """
    return render_template_string(render_page(html), sinh_hoat=SINH_HOAT)

# =============================
# UPLOAD TÀI LIỆU
# =============================
ALLOWED_EXT = {"pdf","docx","xlsx","csv"}
@app.route("/dang_vien/upload", methods=["GET","POST"])
@login_required("dang_vien")
def upload_file():
    username = session["user"]["username"]
    if request.method=="POST":
        f = request.files.get("file")
        if f and f.filename.split(".")[-1].lower() in ALLOWED_EXT:
            filepath = os.path.join(UPLOAD_FOLDER,f.filename)
            f.save(filepath)
            # Giả lập tóm tắt
            DOCS[f.filename]={"summary":f"Tóm tắt nội dung của {f.filename}", "uploader":username}
            flash("Upload thành công và đã tóm tắt nội dung","success")
        else:
            flash("File không hợp lệ","danger")
    html="""
    <h3>Upload tài liệu</h3>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" class="form-control" required>
      <button class="btn btn-success mt-2">Upload</button>
    </form>
    <h5 class="mt-3">Danh sách tài liệu</h5>
    <ul>
      {% for fname, info in docs.items() %}
        <li>{{fname}} - {{info.summary}}</li>
      {% endfor %}
    </ul>
    <a href="/dang_vien" class="btn btn-secondary mt-3">Quay lại</a>
    """
    return render_template_string(render_page(html), docs=DOCS)

# =============================
# CHATBOT
# =============================
@app.route("/dang_vien/chatbot", methods=["GET","POST"])
@login_required("dang_vien")
def chatbot():
    username = session["user"]["username"]
    CHAT_HISTORY.setdefault(username, [])
    answer=""
    if request.method=="POST":
        question = request.form.get("question")
        # Giả lập trả lời từ tóm tắt docs
        answer_list=[]
        for fname,info in DOCS.items():
            if question.lower() in info["summary"].lower():
                answer_list.append(f"{fname}: {info['summary']}")
        if answer_list:
            answer = " | ".join(answer_list)
        else:
            answer = "Không tìm thấy thông tin liên quan"
        CHAT_HISTORY[username].append({"question":question,"answer":answer})
    html="""
    <h3>Chatbot tra cứu tài liệu</h3>
    <form method="post">
      <input class="form-control" name="question" placeholder="Nhập câu hỏi..." required>
      <button class="btn btn-info mt-2">Hỏi</button>
    </form>
    <h5 class="mt-3">Lịch sử hỏi đáp</h5>
    <ul>
      {% for q in history %}
        <li><strong>Câu hỏi:</strong> {{q.question}} <br> <strong>Trả lời:</strong> {{q.answer}}</li>
      {% endfor %}
    </ul>
    <a href="/dang_vien" class="btn btn-secondary mt-3">Quay lại</a>
    """
    return render_template_string(render_page(html), history=CHAT_HISTORY[username])

# =============================
# RUN LOCAL
# =============================
if __name__=="__main__":
    app.run(debug=True)
