from flask import Flask, render_template_string, request, redirect, session, flash, send_from_directory
from functools import wraps
import os
import secrets
import uuid
import pandas as pd
from PyPDF2 import PdfReader
from docx import Document

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ==============================
# USERS DATABASE
# ==============================
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "user_demo": {"password": "Test@123", "role": "dang_vien", "name": "User Demo"},
    "cb1": {"password": "Test@123", "role": "chi_bo", "name": "Chi bộ 1"},
    "dv1": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 1"},
}

# ==============================
# CHAT HISTORY & DOCUMENTS
# ==============================
chat_histories = {}  # session_id -> list of (question, answer)
documents = {}       # filename -> summary text

# ==============================
# CHI BỘ NOTIFICATIONS & ACTIVITIES
# ==============================
chi_bo_notifications = {}  # chi_bo_id -> list of messages
chi_bo_activities = {}     # chi_bo_id -> list of activities

# ==============================
# LOGIN REQUIRED DECORATOR
# ==============================
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

# ==============================
# HELPERS
# ==============================
def summarize_file(filepath):
    text = ""
    if filepath.endswith(".pdf"):
        try:
            reader = PdfReader(filepath)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        except:
            text = "Không đọc được PDF"
    elif filepath.endswith(".docx"):
        try:
            doc = Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
        except:
            text = "Không đọc được DOCX"
    elif filepath.endswith(".csv") or filepath.endswith(".xlsx"):
        try:
            if filepath.endswith(".csv"):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
            text = df.head(5).to_string()
        except:
            text = "Không đọc được dữ liệu"
    else:
        text = "File type not supported."
    return text[:500] + ("..." if len(text) > 500 else "")

def chatbot_reply(session_id, question):
    answers = []
    for fname, summary in documents.items():
        if any(word.lower() in summary.lower() for word in question.split()):
            answers.append(f"[{fname}] {summary}")
    if answers:
        return "\n---\n".join(answers)
    return "Xin lỗi, mình chưa tìm thấy thông tin liên quan."

# ==============================
# ROUTES
# ==============================
@app.route("/")
def index():
    return redirect("/login")

# ----- LOGIN -----
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        pw = request.form.get("password")
        if username in USERS and USERS[username]["password"] == pw:
            session["user"] = {
                "username": username,
                "role": USERS[username]["role"],
                "name": USERS[username]["name"]
            }
            role = USERS[username]["role"]
            if role == "admin":
                return redirect("/admin")
            elif role == "chi_bo":
                return redirect("/chi_bo")
            else:
                return redirect("/dang_vien")
        flash("Sai tài khoản hoặc mật khẩu!", "danger")

    login_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Đăng nhập</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light d-flex align-items-center justify-content-center" style="min-height:100vh;">
      <div class="card p-4 shadow" style="max-width:400px; width:100%;">
        <h3 class="text-center mb-3 text-success">Đăng nhập hệ thống</h3>
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category,msg in messages %}
              <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                {{ msg }}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
              </div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        <form method="post">
          <label class="form-label">Tài khoản</label>
          <input type="text" class="form-control" name="username" required>
          <label class="form-label mt-3">Mật khẩu</label>
          <input type="password" class="form-control" name="password" required>
          <button class="btn btn-success w-100 mt-4">Đăng nhập</button>
        </form>
      </div>
      <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return render_template_string(login_html)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ----- DASHBOARD -----
@app.route("/dashboard")
@login_required()
def dashboard():
    dashboard_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Dashboard</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="d-flex flex-column min-vh-100">
      <header class="bg-light py-3 shadow">
        <div class="container d-flex align-items-center">
          <img src="/static/Logo.png" alt="Logo" height="50" class="me-3">
          <h4 class="mb-0">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        </div>
      </header>
      <div class="container py-5">
        <h3>Xin chào, {{ session.user.name }} ({{ session.user.role }})</h3>
        <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
      </div>
      <footer class="bg-light text-center py-3 mt-auto">
        <div class="container">
          &copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu
        </div>
      </footer>
    </body>
    </html>
    """
    return render_template_string(dashboard_html)

# ==============================
# ADMIN ROUTES
# ==============================
@app.route("/admin")
@login_required("admin")
def admin_home():
    return redirect("/admin/users")

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    admin_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Admin - Users</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="d-flex flex-column min-vh-100">
      <header class="bg-light py-3 shadow">
        <div class="container d-flex align-items-center">
          <img src="/static/Logo.png" alt="Logo" height="50" class="me-3">
          <h4 class="mb-0">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        </div>
      </header>
      <div class="container py-5">
        <h3>Quản lý người dùng</h3>
        <table class="table table-striped mt-3">
          <thead><tr><th>ID</th><th>Tên</th><th>Role</th><th>Hành động</th></tr></thead>
          <tbody>
            {% for username,u in users.items() %}
            <tr>
              <td>{{ username }}</td>
              <td>{{ u.name }}</td>
              <td>{{ u.role }}</td>
              <td>
                {% if username != "admin" and username != "user_demo" %}
                <a href="/admin/users/reset/{{ username }}" class="btn btn-sm btn-warning">Reset Pass</a>
                <a href="/admin/users/delete/{{ username }}" class="btn btn-sm btn-danger">Xóa</a>
                {% else %}
                -
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        <h4 class="mt-4">Thêm người dùng mới</h4>
        <form method="post" action="/admin/users/add">
          <div class="mb-2"><input type="text" class="form-control" name="username" placeholder="ID người dùng" required></div>
          <div class="mb-2"><input type="text" class="form-control" name="name" placeholder="Tên người dùng" required></div>
          <div class="mb-2">
            <select class="form-select" name="role">
              <option value="chi_bo">Chi bộ</option>
              <option value="dang_vien">Đảng viên</option>
            </select>
          </div>
          <button class="btn btn-success">Thêm</button>
        </form>
        <a href="/dashboard" class="btn btn-secondary mt-3">Quay về Dashboard</a>
      </div>
      <footer class="bg-light text-center py-3 mt-auto">
        <div class="container">
          &copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu
        </div>
      </footer>
    </body>
    </html>
    """
    return render_template_string(admin_html, users=USERS)

@app.route("/admin/users/add", methods=["POST"])
@login_required("admin")
def admin_add_user():
    username = request.form.get("username")
    name = request.form.get("name")
    role = request.form.get("role")
    if username in USERS:
        flash("User đã tồn tại!", "danger")
    else:
        USERS[username] = {"password": "Test@123", "role": role, "name": name}
        flash("Đã thêm user mới với mật khẩu Test@123", "success")
    return redirect("/admin/users")

@app.route("/admin/users/delete/<username>")
@login_required("admin")
def admin_delete_user(username):
    if username in USERS:
        del USERS[username]
        flash("Đã xóa người dùng!", "success")
    else:
        flash("User không tồn tại!", "danger")
    return redirect("/admin/users")

@app.route("/admin/users/reset/<username>")
@login_required("admin")
def admin_reset_pass(username):
    if username in USERS and username not in ["admin","user_demo"]:
        USERS[username]["password"] = "Test@123"
        flash("Đã reset mật khẩu về Test@123", "success")
    else:
        flash("Không thể reset mật khẩu user này!", "danger")
    return redirect("/admin/users")


# ==============================
# CHI BỘ ROUTES
# ==============================
@app.route("/chi_bo", methods=["GET","POST"])
@login_required("chi_bo")
def chi_bo_home():
    username = session["user"]["username"]
    if username not in chi_bo_notifications:
        chi_bo_notifications[username] = []
    if username not in chi_bo_activities:
        chi_bo_activities[username] = []

    if request.method == "POST":
        if "notif" in request.form:
            msg = request.form.get("notif")
            chi_bo_notifications[username].append(msg)
            flash("Đã thêm thông báo!", "success")
        elif "activity" in request.form:
            act = request.form.get("activity")
            chi_bo_activities[username].append(act)
            flash("Đã thêm hoạt động sinh hoạt!", "success")

    chi_bo_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Chi bộ</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="d-flex flex-column min-vh-100">
      <header class="bg-light py-3 shadow">
        <div class="container d-flex align-items-center">
          <img src="/static/Logo.png" alt="Logo" height="50" class="me-3">
          <h4 class="mb-0">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        </div>
      </header>
      <div class="container py-5">
        <h3>Xin chào, {{ session.user.name }} (Chi bộ)</h3>
        <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>

        <h4 class="mt-4">Thông báo sinh hoạt</h4>
        <form method="post">
          <input type="text" name="notif" class="form-control mb-2" placeholder="Thêm thông báo">
          <button class="btn btn-primary mb-3">Thêm thông báo</button>
        </form>
        <ul>
        {% for n in notifs %}
          <li>{{ n }}</li>
        {% endfor %}
        </ul>

        <h4 class="mt-4">Thêm hoạt động sinh hoạt</h4>
        <form method="post">
          <input type="text" name="activity" class="form-control mb-2" placeholder="Thêm hoạt động">
          <button class="btn btn-success mb-3">Thêm hoạt động</button>
        </form>
        <ul>
        {% for a in activities %}
          <li>{{ a }}</li>
        {% endfor %}
        </ul>
      </div>
      <footer class="bg-light text-center py-3 mt-auto">
        <div class="container">&copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu</div>
      </footer>
    </body>
    </html>
    """
    return render_template_string(chi_bo_html, notifs=chi_bo_notifications[username], activities=chi_bo_activities[username])

# ==============================
# ĐẢNG VIÊN ROUTES
# ==============================
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    username = session["user"]["username"]
    # Chi bộ mà dv thuộc quyền
    chi_bo = "cb1"  # demo: đơn giản map dv1 -> cb1
    activities = chi_bo_activities.get(chi_bo, [])
    dang_vien_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Đảng viên</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="d-flex flex-column min-vh-100">
      <header class="bg-light py-3 shadow">
        <div class="container d-flex align-items-center">
          <img src="/static/Logo.png" alt="Logo" height="50" class="me-3">
          <h4 class="mb-0">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        </div>
      </header>
      <div class="container py-5">
        <h3>Xin chào, {{ session.user.name }} (Đảng viên)</h3>
        <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>

        <h4 class="mt-4">Hoạt động sinh hoạt của bạn và chi bộ</h4>
        <ul>
          {% for a in activities %}
            <li>{{ a }}</li>
          {% endfor %}
        </ul>
      </div>
      <footer class="bg-light text-center py-3 mt-auto">
        <div class="container">&copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu</div>
      </footer>
    </body>
    </html>
    """
    return render_template_string(dang_vien_html, activities=activities)

# ==============================
# UPLOAD FILE & CHATBOT
# ==============================
@app.route("/upload", methods=["GET","POST"])
@login_required()
def upload_file():
    session_id = session["user"]["username"]
    if session_id not in chat_histories:
        chat_histories[session_id] = []

    if request.method == "POST":
        f = request.files.get("file")
        if f:
            filename = str(uuid.uuid4()) + "_" + f.filename
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            f.save(filepath)
            summary = summarize_file(filepath)
            documents[filename] = summary
            flash("Upload thành công! Nội dung tóm tắt:", "success")
            flash(summary, "info")

    upload_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Upload & Chatbot</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="d-flex flex-column min-vh-100">
      <header class="bg-light py-3 shadow">
        <div class="container d-flex align-items-center">
          <img src="/static/Logo.png" alt="Logo" height="50" class="me-3">
          <h4 class="mb-0">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        </div>
      </header>
      <div class="container py-5">
        <h3>Upload tài liệu</h3>
        <form method="post" enctype="multipart/form-data">
          <input type="file" name="file" class="form-control mb-2">
          <button class="btn btn-primary">Upload</button>
        </form>

        <h3 class="mt-4">Chatbot hỏi về tài liệu</h3>
        <form method="post" action="/chat">
          <input type="text" name="question" class="form-control mb-2" placeholder="Nhập câu hỏi">
          <button class="btn btn-success">Hỏi Chatbot</button>
        </form>

        <h4 class="mt-4">Lịch sử hỏi đáp</h4>
        <ul>
        {% for q,a in chats %}
          <li><b>Câu hỏi:</b> {{ q }} <br> <b>Trả lời:</b> {{ a }}</li>
        {% endfor %}
        </ul>
      </div>
      <footer class="bg-light text-center py-3 mt-auto">
        <div class="container">&copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu</div>
      </footer>
    </body>
    </html>
    """
    return render_template_string(upload_html, chats=chat_histories[session_id])

@app.route("/chat", methods=["POST"])
@login_required()
def chat():
    session_id = session["user"]["username"]
    question = request.form.get("question")
    answer = chatbot_reply(session_id, question)
    chat_histories[session_id].append((question, answer))
    return redirect("/upload")

# ==============================
# RUN LOCAL
# ==============================
if __name__ == "__main__":
    app.run(debug=True)








