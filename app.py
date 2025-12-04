from flask import Flask, render_template_string, request, redirect, session, flash
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# =============================
#  FAKE DATABASE DEMO
# =============================
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "user_demo": {"password": "Test@123", "role": "dang_vien", "name": "User Demo"},
    "cb1": {"password": "Test@123", "role": "chi_bo", "name": "Chi bộ 1"},
    "dv1": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 1", "chi_bo": "cb1"},
    "dv2": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 2", "chi_bo": "cb1"},
}

# Lưu thông báo và hoạt động sinh hoạt
THONG_BAO_CHI_BO = {
    "cb1": []  # list các dict { "tieu_de": ..., "noi_dung": ... }
}

SINH_HOAT = {
    "dv1": [],  # list các dict { "ngay": ..., "hoat_dong": ... }
    "dv2": [],
    "user_demo": []
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
#  HEADER + FOOTER TEMPLATE
# =============================
HEADER_HTML = """
<nav class="navbar navbar-expand-lg navbar-dark bg-success">
  <div class="container-fluid">
    <a class="navbar-brand" href="/dashboard">HỆ THỐNG QLNS - ĐẢNG VIÊN</a>
    <div class="d-flex">
      <span class="navbar-text text-light me-3">Xin chào, {{ session.user.name }}</span>
      <a href="/logout" class="btn btn-outline-light btn-sm">Đăng xuất</a>
    </div>
  </div>
</nav>
"""

FOOTER_HTML = """
<footer class="text-center py-3 bg-light mt-5">
  <small>© 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN</small>
</footer>
"""

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
                "name": USERS[username]["name"],
            }
            if USERS[username]["role"] == "admin":
                return redirect("/admin")
            elif USERS[username]["role"] == "chi_bo":
                return redirect("/chi_bo")
            else:
                return redirect("/dang_vien")
        flash("Sai tài khoản hoặc mật khẩu!", "danger")

    login_html = f"""
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
          <p class="mt-3 text-muted small">Demo login: <strong>user_demo / Test@123</strong></p>
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
    dashboard_html = HEADER_HTML + """
    <div class="container py-5">
      <h3>Xin chào, {{ session.user.name }}</h3>
      <p>Chức năng hệ thống: <strong>{{ session.user.role }}</strong></p>
    </div>
    """ + FOOTER_HTML
    return render_template_string(dashboard_html)

# =============================
#  ADMIN ROUTES
# =============================
@app.route("/admin")
@login_required("admin")
def admin_home():
    return redirect("/admin/users")

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    admin_html = HEADER_HTML + """
    <div class="container py-5">
      <h3>Quản lý người dùng</h3>
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
              {% if username not in ['admin','user_demo'] %}
                <a href="/admin/users/reset/{{ username }}" class="btn btn-sm btn-warning">Reset Pass</a>
              {% endif %}
              {% if username not in ['admin','user_demo'] %}
                <a href="/admin/users/delete/{{ username }}" class="btn btn-sm btn-danger">Xóa</a>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <a href="/dashboard" class="btn btn-secondary mt-3">Dashboard</a>
    </div>
    """ + FOOTER_HTML
    return render_template_string(admin_html, users=USERS)

@app.route("/admin/users/delete/<username>")
@login_required("admin")
def admin_delete_user(username):
    if username in USERS and username not in ["admin","user_demo"]:
        del USERS[username]
        flash("Đã xóa người dùng!", "success")
    else:
        flash("Không thể xóa user này!", "danger")
    return redirect("/admin/users")

@app.route("/admin/users/reset/<username>")
@login_required("admin")
def admin_reset_user(username):
    if username in USERS and username not in ["admin","user_demo"]:
        USERS[username]["password"] = "Test@123"
        flash(f"Đã reset mật khẩu {username} về Test@123", "success")
    else:
        flash("Không thể reset user này!", "danger")
    return redirect("/admin/users")

# =============================
#  CHI BỘ ROUTE
# =============================
@app.route("/chi_bo", methods=["GET","POST"])
@login_required("chi_bo")
def chi_bo_home():
    chi_bo_id = session["user"]["username"]
    if request.method == "POST":
        tieu_de = request.form.get("tieu_de")
        noi_dung = request.form.get("noi_dung")
        dv_username = request.form.get("dv_username")
        if dv_username:
            if dv_username in SINH_HOAT:
                SINH_HOAT[dv_username].append({"hoat_dong": noi_dung})
                flash(f"Đã thêm hoạt động cho {dv_username}", "success")
            else:
                flash("Đảng viên không tồn tại!", "danger")
        else:
            THONG_BAO_CHI_BO[chi_bo_id].append({"tieu_de": tieu_de, "noi_dung": noi_dung})
            flash("Đã thêm thông báo chi bộ!", "success")

    dv_cua_chi_bo = [u for u, v in USERS.items() if v.get("chi_bo") == chi_bo_id]
    chi_bo_html = HEADER_HTML + """
    <div class="container py-5">
      <h3>Chi bộ: {{ session.user.name }}</h3>
      <h5>Thông báo sinh hoạt chi bộ</h5>
      <ul class="list-group mb-3">
        {% for tb in thong_bao %}
          <li class="list-group-item"><strong>{{ tb.tieu_de }}</strong>: {{ tb.noi_dung }}</li>
        {% else %}
          <li class="list-group-item">Chưa có thông báo</li>
        {% endfor %}
      </ul>

      <h5>Hoạt động sinh hoạt đảng viên</h5>
      <ul class="list-group mb-3">
        {% for dv in dv_cua_chi_bo %}
          <li><strong>{{ users[dv].name }}</strong>
            <ul>
              {% for sh in sinh_hoat[dv] %}
                <li>{{ sh.hoat_dong }}</li>
              {% else %}
                <li>Chưa có hoạt động</li>
              {% endfor %}
            </ul>
          </li>
        {% endfor %}
      </ul>

      <h5>Thêm thông báo / hoạt động</h5>
      <form method="post" class="mb-3">
        <div class="mb-2">
          <label class="form-label">Tiêu đề (để trống nếu thêm hoạt động cá nhân)</label>
          <input class="form-control" name="tieu_de">
        </div>
        <div class="mb-2">
          <label class="form-label">Nội dung</label>
          <textarea class="form-control" name="noi_dung" required></textarea>
        </div>
        <div class="mb-2">
          <label class="form-label">Tên Đảng viên (chỉ khi thêm hoạt động riêng)</label>
          <input class="form-control" name="dv_username">
        </div>
        <button class="btn btn-success mt-2">Thêm</button>
      </form>

      <a href="/dashboard" class="btn btn-secondary mt-3">Dashboard</a>
    </div>
    """ + FOOTER_HTML
    return render_template_string(chi_bo_html,
                                  thong_bao=THONG_BAO_CHI_BO[chi_bo_id],
                                  dv_cua_chi_bo=dv_cua_chi_bo,
                                  sinh_hoat=SINH_HOAT,
                                  users=USERS)

# =============================
#  ĐẢNG VIÊN ROUTE
# =============================
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    username = session["user"]["username"]
    chi_bo_id = USERS[username].get("chi_bo")
    dang_vien_html = HEADER_HTML + """
    <div class="container py-5">
      <h3>Đảng viên: {{ session.user.name }}</h3>
      <h5>Thông báo chi bộ</h5>
      <ul class="list-group mb-3">
        {% for tb in thong_bao %}
          <li class="list-group-item"><strong>{{ tb.tieu_de }}</strong>: {{ tb.noi_dung }}</li>
        {% else %}
          <li class="list-group-item">Chưa có thông báo</li>
        {% endfor %}
      </ul>

      <h5>Hoạt động cá nhân</h5>
      <ul class="list-group mb-3">
        {% for sh in sinh_hoat %}
          <li>{{ sh.hoat_dong }}</li>
        {% else %}
          <li>Chưa có hoạt động</li>
        {% endfor %}
      </ul>

      <a href="/dashboard" class="btn btn-secondary mt-3">Dashboard</a>
    </div>
    """ + FOOTER_HTML
    return render_template_string(dang_vien_html,
                                  thong_bao=THONG_BAO_CHI_BO.get(chi_bo_id, []),
                                  sinh_hoat=SINH_HOAT.get(username, []))

# =============================
#  RUN LOCAL
# =============================
if __name__ == "__main__":
    app.run(debug=True)
