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
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Đăng nhập</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
      <div class="container d-flex align-items-center justify-content-center" style="min-height: 100vh;">
        <div class="card p-4 shadow" style="max-width: 400px; width: 100%;">
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
    <body class="bg-light">
      <div class="container py-5">
        <h3>Xin chào, {{ session.user.name }}</h3>
        <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(dashboard_html)


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
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Admin - Users</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
      <div class="container py-5">
        <h3>Quản lý người dùng</h3>
        <table class="table table-striped mt-3">
          <thead>
            <tr>
              <th>ID</th>
              <th>Tên</th>
              <th>Role</th>
              <th>Hành động</th>
            </tr>
          </thead>
          <tbody>
            {% for username, u in users.items() %}
            <tr>
              <td>{{ username }}</td>
              <td>{{ u.name }}</td>
              <td>{{ u.role }}</td>
              <td>
                <a href="/admin/users/delete/{{ username }}" class="btn btn-sm btn-danger">Xóa</a>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(admin_html, users=USERS)


@app.route("/admin/users/delete/<username>")
@login_required("admin")
def admin_delete_user(username):
    if username in USERS:
        del USERS[username]
        flash("Đã xóa người dùng!", "success")
    else:
        flash("User không tồn tại!", "danger")
    return redirect("/admin/users")


# =============================
#  CHI BỘ ROUTE
# =============================
@app.route("/chi_bo")
@login_required("chi_bo")
def chi_bo_home():
    chi_bo_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Chi bộ</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
      <div class="container py-5">
        <h3>Xin chào, {{ session.user.name }} (Chi bộ)</h3>
        <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(chi_bo_html)


# =============================
#  ĐẢNG VIÊN ROUTE
# =============================
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    dang_vien_html = """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Đảng viên</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
      <div class="container py-5">
        <h3>Xin chào, {{ session.user.name }} (Đảng viên)</h3>
        <a href="/logout" class="btn btn-danger mt-3">Đăng xuất</a>
      </div>
    </body>
    </html>
    """
    return render_template_string(dang_vien_html)


# =============================
#  RUN LOCAL
# =============================
if __name__ == "__main__":
    app.run(debug=True)
