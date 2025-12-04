from flask import Flask, render_template_string, request, redirect, session, flash, send_from_directory, jsonify
from functools import wraps
import os
import re
import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# =============================
# FAKE DATABASE
# =============================
USERS = {
    "admin": {"password": "Test@321", "role": "admin", "name": "Quản trị viên"},
    "user_demo": {"password": "Test@123", "role": "dang_vien", "name": "User Demo"},
    "cb1": {"password": "Test@123", "role": "chi_bo", "name": "Chi bộ 1"},
    "dv1": {"password": "Test@123", "role": "dang_vien", "name": "Đảng viên 1"},
}

SINH_HOAT = {"cb1": []}  # chi_bo_id: list of sinh hoat
THONG_BAO = {"cb1": []}  # chi_bo_id: list of thong bao

UPLOADS = []  # demo upload: {filename,uploader,date,summary}
CHAT_HISTORY = []  # {user, question, answer, timestamp}

# =============================
# DECORATORS
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

def validate_password(pw):
    if len(pw)<8: return False
    if not re.search(r"[A-Z]", pw): return False
    if not re.search(r"[a-z]", pw): return False
    if not re.search(r"[0-9]", pw): return False
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", pw): return False
    return True

# =============================
# LOGIN / LOGOUT
# =============================
@app.route("/")
def index(): return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username = request.form.get("username")
        pw = request.form.get("password")
        if username in USERS and USERS[username]["password"]==pw:
            session["user"] = {"username":username,"role":USERS[username]["role"],"name":USERS[username]["name"]}
            role = USERS[username]["role"]
            if role=="admin": return redirect("/admin")
            elif role=="chi_bo": return redirect("/chi_bo")
            else: return redirect("/dang_vien")
        flash("Sai tài khoản hoặc mật khẩu!", "danger")
    login_html = """
    <!DOCTYPE html><html lang="vi"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng nhập</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="bg-light">
    <div class="container d-flex align-items-center justify-content-center" style="min-height:100vh;">
    <div class="card p-4 shadow" style="max-width:400px;width:100%;">
    <img src="/static/Logo.png" class="mx-auto d-block mb-3" style="height:60px;">
    <h3 class="text-center mb-3 text-success">Đăng nhập hệ thống</h3>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}{% for category,msg in messages %}
      <div class="alert alert-{{category}} alert-dismissible fade show" role="alert">
        {{msg}}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>{% endfor %}{% endif %}{% endwith %}
    <form method="post">
      <label class="form-label">Tài khoản</label>
      <input type="text" class="form-control" name="username" required>
      <label class="form-label mt-3">Mật khẩu</label>
      <input type="password" class="form-control" name="password" required>
      <button class="btn btn-success w-100 mt-4">Đăng nhập</button>
    </form>
    </div></div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    </body></html>
    """
    return render_template_string(login_html)

@app.route("/logout")
def logout(): session.clear(); return redirect("/login")

# =============================
# DASHBOARD
# =============================
@app.route("/dashboard")
@login_required()
def dashboard():
    return f"Xin chào {session['user']['name']} - Role: {session['user']['role']}"

# =============================
# ADMIN
# =============================
@app.route("/admin")
@login_required("admin")
def admin_home(): return redirect("/admin/users")

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    admin_html = """
    <!DOCTYPE html><html lang="vi"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - Users</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head><body class="d-flex flex-column min-vh-100 bg-light">
    <header class="bg-white shadow-sm py-2 mb-4">
      <div class="container d-flex align-items-center">
        <img src="/static/Logo.png" style="height:50px;" class="me-3">
        <h4 class="mb-0">Admin - Quản lý người dùng</h4>
        <div class="ms-auto">
          <span>{{session.user.name}}</span>
          <a href="/logout" class="btn btn-danger btn-sm ms-2">Đăng xuất</a>
        </div>
      </div>
    </header>
    <div class="container py-5">
      <h3>Danh sách người dùng</h3>
      <table class="table table-striped mt-3">
        <thead><tr><th>ID</th><th>Tên</th><th>Role</th><th>Hành động</th></tr></thead>
        <tbody>
          {% for username,u in users.items() %}
          <tr>
            <td>{{username}}</td>
            <td>{{u.name}}</td>
            <td>{{u.role}}</td>
            <td>
              {% if username!="admin" and username!="user_demo" %}
              <a href="/admin/reset/{{username}}" class="btn btn-sm btn-warning">Reset Pass</a>
              <a href="/admin/delete/{{username}}" class="btn btn-sm btn-danger">Xóa</a>
              {% else %}<span class="text-muted">Không đổi</span>{% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <h4 class="mt-4">Thêm user mới</h4>
      <form method="post" action="/admin/add">
        <div class="mb-2"><input class="form-control" name="username" placeholder="ID user" required></div>
        <div class="mb-2"><input class="form-control" name="name" placeholder="Tên người dùng" required></div>
        <div class="mb-2">
          <select class="form-select" name="role">
            <option value="dang_vien">Đảng viên</option>
            <option value="chi_bo">Chi bộ</option>
          </select>
        </div>
        <button class="btn btn-success">Thêm user</button>
      </form>
    </div>
    <footer class="bg-light text-center py-3 mt-auto">
      <div class="container">&copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu</div>
    </footer>
    </body></html>
    """
    return render_template_string(admin_html, users=USERS)

@app.route("/admin/add", methods=["POST"])
@login_required("admin")
def admin_add_user():
    username = request.form.get("username")
    name = request.form.get("name")
    role = request.form.get("role")
    if username in USERS:
        flash("User đã tồn tại!", "danger")
    else:
        USERS[username] = {"password":"Test@123","role":role,"name":name}
        flash("Đã thêm user mới với mật khẩu mặc định Test@123", "success")
    return redirect("/admin/users")

@app.route("/admin/delete/<username>")
@login_required("admin")
def admin_delete_user(username):
    if username in USERS and username not in ["admin","user_demo"]:
        del USERS[username]
        flash("Đã xóa user!", "success")
    else: flash("Không thể xóa user này!", "danger")
    return redirect("/admin/users")

@app.route("/admin/reset/<username>")
@login_required("admin")
def admin_reset_user(username):
    if username in USERS and username not in ["admin","user_demo"]:
        USERS[username]["password"]="Test@123"
        flash(f"Đã reset mật khẩu user {username} về Test@123", "success")
    else: flash("Không thể reset mật khẩu user này!", "danger")
    return redirect("/admin/users")

# =============================
# CHI BỘ
# =============================
@app.route("/chi_bo")
@login_required("chi_bo")
def chi_bo_home():
    chi_bo_id = session["user"]["username"]
    sinhhoat_list = SINH_HOAT.get(chi_bo_id,[])
    thongbao_list = THONG_BAO.get(chi_bo_id,[])
    html = """
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chi bộ</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body class="d-flex flex-column min-vh-100 bg-light">
    <header class="bg-white shadow-sm py-2 mb-4">
      <div class="container d-flex align-items-center">
        <img src="/static/Logo.png" style="height:50px;" class="me-3">
        <h4 class="mb-0">Chi bộ - {{session.user.name}}</h4>
        <div class="ms-auto">
          <span>{{session.user.name}}</span>
          <a href="/logout" class="btn btn-danger btn-sm ms-2">Đăng xuất</a>
        </div>
      </div>
    </header>
    <div class="container py-5">
      <h4>Thông báo</h4>
      <ul>
        {% for tb in thongbao_list %}
          <li>{{tb}}</li>
        {% else %}<li>Chưa có thông báo</li>{% endfor %}
      </ul>
      <h4 class="mt-4">Sinh hoạt đảng</h4>
      <ul>
        {% for sh in sinhhoat_list %}
          <li>{{sh}}</li>
        {% else %}<li>Chưa có sinh hoạt</li>{% endfor %}
      </ul>
      <h5 class="mt-4">Thêm thông báo</h5>
      <form method="post" action="/chi_bo/add_tb">
        <input class="form-control mb-2" name="noidung" placeholder="Nội dung thông báo" required>
        <button class="btn btn-success">Thêm thông báo</button>
      </form>
      <h5 class="mt-4">Thêm sinh hoạt đảng</h5>
      <form method="post" action="/chi_bo/add_sh">
        <input class="form-control mb-2" name="noidung" placeholder="Nội dung sinh hoạt" required>
        <button class="btn btn-primary">Thêm sinh hoạt</button>
      </form>
    </div>
    <footer class="bg-light text-center py-3 mt-auto">
      <div class="container">&copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN</div>
    </footer></body></html>
    """
    return render_template_string(html, sinhhoat_list=sinhhoat_list, thongbao_list=thongbao_list)

@app.route("/chi_bo/add_tb", methods=["POST"])
@login_required("chi_bo")
def chi_bo_add_tb():
    cb = session["user"]["username"]
    noidung = request.form.get("noidung")
    THONG_BAO.setdefault(cb,[]).append(noidung)
    flash("Đã thêm thông báo", "success")
    return redirect("/chi_bo")

@app.route("/chi_bo/add_sh", methods=["POST"])
@login_required("chi_bo")
def chi_bo_add_sh():
    cb = session["user"]["username"]
    noidung = request.form.get("noidung")
    SINH_HOAT.setdefault(cb,[]).append(noidung)
    flash("Đã thêm sinh hoạt đảng", "success")
    return redirect("/chi_bo")

# =============================
# DANG VIEN
# =============================
@app.route("/dang_vien")
@login_required("dang_vien")
def dang_vien_home():
    # demo user xem thông báo và sinh hoạt cá nhân
    user = session["user"]["username"]
    html = f"""
    <!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đảng viên</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body class="d-flex flex-column min-vh-100 bg-light">
    <header class="bg-white shadow-sm py-2 mb-4">
      <div class="container d-flex align-items-center">
        <img src="/static/Logo.png" style="height:50px;" class="me-3">
        <h4 class="mb-0">Đảng viên - {session['user']['name']}</h4>
        <div class="ms-auto">
          <span>{session['user']['name']}</span>
          <a href="/logout" class="btn btn-danger btn-sm ms-2">Đăng xuất</a>
        </div>
      </div>
    </header>
    <div class="container py-5">
      <h4>Thông báo liên quan</h4>
      <ul>
      {% for cb,tbs in thongbao.items() %}
        {% for tb in tbs %}<li>{{tb}}</li>{% endfor %}
      {% endfor %}
      </ul>
    </div>
    <footer class="bg-light text-center py-3 mt-auto">
      <div class="container">&copy; 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN</div>
    </footer>
    </body></html>
    """
    return render_template_string(html, thongbao=THONG_BAO)

# =============================
# RUN APP
# =============================
if __name__=="__main__":
    app.run(debug=True)
