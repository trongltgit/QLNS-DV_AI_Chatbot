from flask import Flask, request, session, redirect, url_for, render_template_string, flash
import os
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")
DB_PATH = "app_singlefile.db"

# --- Templates ---
TEMPLATES = {
    "base": """
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{% block title %}QLNS{% endblock %}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
    <div class="container py-4">
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for msg in messages %}
              <div class="alert alert-warning">{{ msg }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
    </body>
    </html>
    """,
    "login": """
    {% extends "base" %}
    {% block title %}Đăng nhập{% endblock %}
    {% block content %}
    <h2>Đăng nhập</h2>
    <form method="post">
      <div class="mb-3">
        <label for="username" class="form-label">Username</label>
        <input type="text" name="username" class="form-control" required>
      </div>
      <div class="mb-3">
        <label for="password" class="form-label">Password</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <button class="btn btn-primary">Đăng nhập</button>
    </form>
    {% endblock %}
    """,
    "admin_dashboard": """
    {% extends "base" %}
    {% block title %}Admin Dashboard{% endblock %}
    {% block content %}
    <h2>Chào, {{ user.username }} (Admin)</h2>
    <a href="{{ url_for('logout') }}" class="btn btn-secondary mb-3">Đăng xuất</a>
    <h3>Danh sách người dùng</h3>
    <table class="table table-bordered">
      <tr><th>ID</th><th>Username</th><th>Role</th></tr>
      {% for u in users %}
      <tr><td>{{ u[0] }}</td><td>{{ u[1] }}</td><td>{{ u[2] }}</td></tr>
      {% endfor %}
    </table>
    {% endblock %}
    """,
    "chi_bo_list": """
    {% extends "base" %}
    {% block title %}Danh sách chi bộ{% endblock %}
    {% block content %}
    <h2>Danh sách chi bộ</h2>
    <ul>
    {% for chi in chibos %}
      <li>{{ chi[1] }} (<a href="{{ url_for('chi_bo_detail', chi_bo_id=chi[0]) }}">Chi tiết</a>)</li>
    {% endfor %}
    </ul>
    {% endblock %}
    """,
    "chi_bo_detail": """
    {% extends "base" %}
    {% block title %}Chi tiết chi bộ{% endblock %}
    {% block content %}
    <h2>Chi bộ: {{ chi_bo[1] }}</h2>
    <ul>
      {% for dv in members %}
      <li>{{ dv[1] }} - {{ dv[2] }}</li>
      {% endfor %}
    </ul>
    <a href="{{ url_for('chi_bo_list') }}">Quay lại</a>
    {% endblock %}
    """
}

# --- Database setup ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Users table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")
    # ChiBo table
    c.execute("""CREATE TABLE IF NOT EXISTS chibos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )""")
    # DangVien table
    c.execute("""CREATE TABLE IF NOT EXISTS dangvien (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        position TEXT,
        chi_bo_id INTEGER,
        FOREIGN KEY(chi_bo_id) REFERENCES chibos(id)
    )""")
    # Create default admin
    c.execute("INSERT OR IGNORE INTO users (username,password,role) VALUES ('admin','admin','admin')")
    conn.commit()
    conn.close()

init_db()

# --- Routes ---
@app.route("/")
def index():
    if session.get("user"):
        user = session["user"]
        if user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("chi_bo_list"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username,password))
        user = c.fetchone()
        conn.close()
        if user:
            session["user"] = {"id": user["id"], "username": user["username"], "role": user["role"]}
            return redirect(url_for("index"))
        else:
            flash("Sai username hoặc password")
    return render_template_string(TEMPLATES["login"])

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/admin")
def admin_dashboard():
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return render_template_string(TEMPLATES["admin_dashboard"], user=session["user"], users=users)

@app.route("/chi_bo")
def chi_bo_list():
    conn = get_db()
    chibos = conn.execute("SELECT * FROM chibos").fetchall()
    conn.close()
    return render_template_string(TEMPLATES["chi_bo_list"], chibos=chibos)

@app.route("/chi_bo/<int:chi_bo_id>")
def chi_bo_detail(chi_bo_id):
    conn = get_db()
    chi_bo = conn.execute("SELECT * FROM chibos WHERE id=?", (chi_bo_id,)).fetchone()
    members = conn.execute("SELECT * FROM dangvien WHERE chi_bo_id=?", (chi_bo_id,)).fetchall()
    conn.close()
    return render_template_string(TEMPLATES["chi_bo_detail"], chi_bo=chi_bo, members=members)

@app.route("/upload", methods=["GET","POST"])
def upload_file():
    if request.method == "POST":
        f = request.files.get("file")
        if f:
            filename = secure_filename(f.filename)
            save_path = os.path.join("uploads", filename)
            os.makedirs("uploads", exist_ok=True)
            f.save(save_path)
            flash(f"Đã upload {filename}")
            return redirect(url_for("upload_file"))
    return render_template_string("""
    {% extends "base" %}
    {% block title %}Upload File{% endblock %}
    {% block content %}
    <h2>Upload File</h2>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" required>
      <button class="btn btn-primary">Upload</button>
    </form>
    {% endblock %}
    """)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
