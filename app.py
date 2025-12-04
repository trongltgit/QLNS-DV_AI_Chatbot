from flask import Flask, request, redirect, session, url_for, flash, render_template_string
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# =============================
# USERS DEMO (Bạn có thể thay, thêm, xoá)
# =============================
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "cb1": {"password": "Test@123", "role": "chi_bo", "name": "Chi bộ 1"},
    "dv1": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 1"},
}

# =============================
# HTML TEMPLATES INLINE
# =============================
TPL_BASE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">

<nav class="navbar navbar-dark bg-dark">
  <div class="container">
    <a class="navbar-brand" href="#">QLNS - Đảng viên</a>
    {% if session.user %}
        <a href="/logout" class="btn btn-danger">Đăng xuất</a>
    {% endif %}
  </div>
</nav>

<div class="container py-4">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat, msg in messages %}
          <div class="alert alert-{{ cat }}">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {{ content }}
</div>

</body>
</html>
"""

# =============================
# LOGIN PAGE
# =============================
TPL_LOGIN = """
<h3 class="text-center mb-3">Đăng nhập hệ thống</h3>
<div class="card p-4 mx-auto" style="max-width: 400px;">
    <form method="post">
        <label class="form-label">Tài khoản</label>
        <input type="text" class="form-control" name="username" required>

        <label class="form-label mt-3">Mật khẩu</label>
        <input type="password" class="form-control" name="password" required>

        <button class="btn btn-primary w-100 mt-4">Đăng nhập</button>
    </form>
</div>
"""

# =============================
# ADMIN PAGE
# =============================
TPL_ADMIN = """
<h2>Trang quản trị</h2>
<p>Xin chào: <strong>{{ session.user.name }}</strong></p>

<h4 class="mt-4">Danh sách người dùng</h4>
<table class="table table-bordered">
  <tr><th>Username</th><th>Role</th><th>Tên</th><th>Xóa</th></tr>

  {% for username, data in users.items() %}
  <tr>
      <td>{{ username }}</td>
      <td>{{ data.role }}</td>
      <td>{{ data.name }}</td>
      <td>
        {% if username != "admin" %}
          <a class="btn btn-danger btn-sm" href="/admin/users/delete/{{ username }}">Xóa</a>
        {% endif %}
      </td>
  </tr>
  {% endfor %}
</table>
"""

# =============================
# CHI BỘ PAGE
# =============================
TPL_CHIBO = """
<h2>Trang Chi bộ</h2>
<p>Xin chào: <strong>{{ session.user.name }}</strong></p>
"""

# =============================
# ĐẢNG VIÊN PAGE
# =============================
TPL_DANGVIEN = """
<h2>Trang Đảng viên</h2>
<p>Xin chào: <strong>{{ session.user.name }}</strong></p>
"""

# =============================
# Helper: render inline template
# =============================
def render_page(title, tpl, **kwargs):
    return render_template_string(
        TPL_BASE,
        title=title,
        content=render_template_string(tpl, **kwargs),
    )

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
                return redirect("/")

            return fn(*args, **kwargs)
        return decorated
    return wrapper


# =============================
# ROUTES
# =============================

@app.route("/")
def index():
    if "user" in session:
        role = session["user"]["role"]
        if role == "admin":
            return redirect("/admin")
        if role == "chi_bo":
            return redirect("/chi_bo")
        if role == "dang_vien":
            return redirect("/dang_vien")
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        pw = request.form.get("password")

        if username in USERS and USERS[username]["password"] == pw:
            session["user"] = {
                "username": username,
                "role": USERS[username]["role"],
                "name": USERS[username]["name"],
            }
            return redirect("/")

        flash("Sai tài khoản hoặc mật khẩu!", "danger")

    return render_page("Đăng nhập", TPL_LOGIN)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# -------- ADMIN ----------
@app.route("/admin")
@login_required("admin")
def admin_home():
    return render_page("Quản trị", TPL_ADMIN, users=USERS)


@app.route("/admin/users/delete/<username>")
@login_required("admin")
def admin_delete_user(username):
    if username in USERS and username != "admin":
        del USERS[username]
        flash("Đã xóa người dùng!", "success")
    else:
        flash("Không thể xóa!", "danger")

    return redirect("/admin")


# -------- CHI BỘ ----------
@app.route("/chi_bo")
@login_required("chi_bo")
def chi_bo_home():
    return render_page("Chi bộ", TPL_CHIBO)


# -------- ĐẢNG VIÊN ----------
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    return render_page("Đảng viên", TPL_DANGVIEN)


# =============================
# RUN
# =============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
