from flask import Flask, render_template_string, request, redirect, session, flash
from functools import wraps
import os

app = Flask(__name__)

# SECRET KEY từ environment variable trên Render
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# =============================
#  FAKE DATABASE DEMO
# =============================
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "cb1": {"password": "Test@123", "role": "chi_bo", "name": "Chi bộ 1"},
    "dv1": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 1"},
    "user_demo": {"password": "Test@123", "role": "dang_vien", "name": "User Demo"},
}

# =============================
#  LOGIN REQUIRED DECORATOR
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
#  HEADER + FOOTER HTML
# =============================
def render_page(content_html, title="HỆ THỐNG QLNS - ĐẢNG VIÊN"):
    base_html = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{title}</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
        body {{ display: flex; flex-direction: column; min-height: 100vh; }}
        main {{ flex: 1; }}
      </style>
    </head>
    <body class="bg-light">
      <header class="bg-success text-white py-2 mb-4">
        <div class="container d-flex align-items-center">
          <img src="/static/Logo.png" alt="Logo" height="50" class="me-3">
          <h4 class="mb-0">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        </div>
      </header>
      <main class="container">
        {content_html}
      </main>
      <footer class="bg-light text-center py-3 mt-auto">
        <div class="container">
          &copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu
        </div>
      </footer>
      <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return base_html

# =============================
#  ROUTES
# =============================
@app.route("/")
def index():
    return redirect("/login")

# ----- LOGIN -----
@app.route("/login", methods=["GET", "POST"])
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
    <div class="card p-4 shadow mx-auto" style="max-width:400px;">
      <h3 class="text-center mb-3 text-success">Đăng nhập hệ thống</h3>
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, msg in messages %}
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
    dashboard_html = """
    <h3>Xin chào, {{ session.user.name }}</h3>
    <p>Role: {{ session.user.role }}</p>
    <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
    """
    return render_template_string(render_page(dashboard_html, title="Dashboard"))

# =============================
#  ADMIN ROUTES
# =============================
@app.route("/admin")
@login_required("admin")
def admin_home():
    return admin_users()

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    admin_html = """
    <h3>Quản lý người dùng</h3>
    <table class="table table-striped mt-3">
      <thead>
        <tr><th>ID</th><th>Tên</th><th>Role</th><th>Hành động</th></tr>
      </thead>
      <tbody>
        {% for username, u in users.items() %}
        <tr>
          <td>{{ username }}</td>
          <td>{{ u.name }}</td>
          <td>{{ u.role }}</td>
          <td>
            {% if username not in ['admin','user_demo'] %}
            <a href="/admin/users/delete/{{ username }}" class="btn btn-sm btn-danger">Xóa</a>
            {% else %}
            ---
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
    """
    return render_template_string(render_page(admin_html, title="Admin - Users"), users=USERS)

@app.route("/admin/users/delete/<username>")
@login_required("admin")
def admin_delete_user(username):
    if username in USERS and username not in ['admin','user_demo']:
        del USERS[username]
        flash("Đã xóa người dùng!", "success")
    else:
        flash("Không thể xóa user này!", "danger")
    return redirect("/admin/users")

# =============================
#  CHI BỘ ROUTE
# =============================
@app.route("/chi_bo")
@login_required("chi_bo")
def chi_bo_home():
    chi_bo_html = """
    <h3>Xin chào, {{ session.user.name }} (Chi bộ)</h3>
    <p>Danh sách sinh hoạt Đảng và hoạt động liên quan của chi bộ.</p>
    <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
    """
    return render_template_string(render_page(chi_bo_html, title="Chi bộ"))

# =============================
#  ĐẢNG VIÊN ROUTE
# =============================
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    dang_vien_html = """
    <h3>Xin chào, {{ session.user.name }} (Đảng viên)</h3>
    <p>Xem sinh hoạt Đảng và các thông báo liên quan.</p>
    <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
    """
    return render_template_string(render_page(dang_vien_html, title="Đảng viên"))

# =============================
#  RUN LOCAL
# =============================
if __name__ == "__main__":
    app.run(debug=True)
