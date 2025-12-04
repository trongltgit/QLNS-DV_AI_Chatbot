# app.py - Single-file Flask app with embedded templates.
# Mode: OpenAI API (RAG + Chat). Designed for Render Free.
import os
import io
import json
import sqlite3
import numpy as np
from datetime import datetime
from flask import Flask, request, session, redirect, url_for, flash, send_from_directory, jsonify, make_response
from werkzeug.utils import secure_filename
from jinja2 import Environment, DictLoader, select_autoescape

# Optional parsers
try:
    import PyPDF2
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except Exception:
    PANDAS_AVAILABLE = False

# OpenAI
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# Config
UPLOAD_FOLDER = "uploads"
DB_PATH = "app_singlefile.db"
ALLOWED_EXT = {"pdf", "txt", "md", "docx", "csv", "xlsx"}
SECRET_KEY = os.environ.get("FLASK_SECRET", os.environ.get("SECRET_KEY", "dev-secret-key-2025"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

if OPENAI_AVAILABLE and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# --- Templates embedded ---
TEMPLATES = {
"base.html": """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}Hệ thống QLNS{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    :root{--primary:#0B6E3B;--accent:#3AA14A}
    body{font-family:Inter,Arial,Helvetica;background:#f4f6f8;margin:0;color:#222}
    header{background:#fff;padding:12px;border-bottom:1px solid #e6eaed}
    .brand {display:flex;gap:12px;align-items:center}
    .brand .logo {width:56px;height:56px;border-radius:8px;background:var(--primary);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700}
    .navbar-custom{background:var(--primary);padding:8px;color:#fff}
    .card{background:#fff;border-radius:8px;padding:16px;margin-bottom:16px}
  </style>
  {% block extra_head %}{% endblock %}
</head>
<body>
  <header class="container d-flex justify-content-between align-items-center">
    <div class="brand">
      <div class="logo">LTT</div>
      <div>
        <h4 style="margin:0;color:var(--primary)">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        <div class="text-muted small">Chatbot AI & Quản lý Sinh hoạt</div>
      </div>
    </div>
    <div>
      {% if user %}
        <div class="text-end">
          <div style="font-weight:600;color:var(--accent)">{{ user.get('full_name') or user.get('username') }}</div>
          <div class="small text-muted">{{ user.get('role')|upper }}</div>
          <div style="margin-top:6px"><a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logout') }}">Đăng xuất</a></div>
        </div>
      {% else %}
        <a class="btn btn-outline-primary btn-sm" href="{{ url_for('login') }}">Đăng nhập</a>
      {% endif %}
    </div>
  </header>

  {% if user %}
  <div class="navbar-custom">
    <div class="container d-flex justify-content-between align-items-center">
      <div>
        <a class="text-white me-3" href="{{ url_for('admin_index') }}">Dashboard</a>
        <a class="text-white me-3" href="{{ url_for('chi_bo_list') }}">Chi bộ</a>
        <a class="text-white me-3" href="{{ url_for('dang_vien_list') }}">Đảng viên</a>
        <a class="text-white me-3" href="{{ url_for('rag_chat') }}">Chatbot AI</a>
        <a class="text-white" href="{{ url_for('upload_page') }}">Upload</a>
      </div>
      <div>
        {% if user.role == 'admin' %}
          <a class="text-white" href="{{ url_for('admin_user_list') }}">Quản lý user</a>
        {% endif %}
      </div>
    </div>
  </div>
  {% endif %}

  <main class="container my-4">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, msg in messages %}
          <div class="alert alert-{{ 'warning' if category=='warn' else category }}">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>

  <footer class="text-center py-3">
    © 2025 - QLNS - LTT
  </footer>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
""",
"login.html": """
{% extends "base.html" %}
{% block title %}Đăng nhập{% endblock %}
{% block content %}
<div class="card mx-auto" style="max-width:420px">
  <h4>Đăng nhập</h4>
  <form method="post">
    <div class="mb-3"><label class="form-label">Tên đăng nhập</label><input class="form-control" name="username" required></div>
    <div class="mb-3"><label class="form-label">Mật khẩu</label><input class="form-control" name="password" type="password" required></div>
    <div class="d-flex justify-content-between align-items-center">
      <button class="btn btn-primary">Đăng nhập</button>
      <a href="#" onclick="alert('Demo: admin/admin, user_demo/user123')">?</a>
    </div>
  </form>
</div>
{% endblock %}
""",
"admin_dashboard.html": """
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="card">
  <h4>Xin chào {{ user.full_name or user.username }}</h4>
  <p class="small text-muted">Số chi bộ: {{ stats.chibo_count }} — Đảng viên: {{ stats.dv_count }} — Tài liệu: {{ stats.doc_count }}</p>
  <div class="mt-3">
    <a class="btn btn-primary me-2" href="{{ url_for('chi_bo_list') }}">Quản lý Chi bộ</a>
    <a class="btn btn-primary me-2" href="{{ url_for('dang_vien_list') }}">Quản lý Đảng viên</a>
    <a class="btn btn-success me-2" href="{{ url_for('upload_page') }}">Upload</a>
    <a class="btn btn-info" href="{{ url_for('rag_chat') }}">Chatbot AI</a>
  </div>
</div>
{% endblock %}
""",
"admin_users.html": """
{% extends "base.html" %}
{% block title %}Quản lý người dùng{% endblock %}
{% block content %}
<div class="card">
  <h4>Người dùng (demo)</h4>
  <form method="post" action="{{ url_for('admin_user_add') }}" class="row g-2 mb-3">
    <div class="col"><input class="form-control" name="username" placeholder="username" required></div>
    <div class="col"><input class="form-control" name="full_name" placeholder="Họ tên" required></div>
    <div class="col"><input class="form-control" name="password" placeholder="password" required></div>
    <div class="col-auto"><button class="btn btn-success">Thêm</button></div>
  </form>

  <table class="table">
    <thead><tr><th>#</th><th>Username</th><th>Họ tên</th><th>Role</th><th>Hành động</th></tr></thead>
    <tbody>
      {% for u in users %}
        <tr>
          <td>{{ loop.index }}</td>
          <td>{{ u.username }}</td>
          <td>{{ u.full_name or '-' }}</td>
          <td>{{ u.role }}</td>
          <td>
            {% if u.username != 'admin' %}
              <form method="post" action="{{ url_for('admin_user_delete', username=u.username) }}" style="display:inline"><button class="btn btn-sm btn-outline-danger" onclick="return confirm('Xóa?')">Xóa</button></form>
            {% else %}System{% endif %}
          </td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
""",
"chi_bo_list.html": """
{% extends "base.html" %}
{% block title %}Chi bộ{% endblock %}
{% block content %}
<div class="card">
  <div class="d-flex justify-content-between align-items-center">
    <h4>Danh sách Chi bộ</h4>
    <form method="post" action="{{ url_for('chi_bo_create') }}" class="d-flex gap-2">
      <input name="name" class="form-control form-control-sm" placeholder="Tên chi bộ" required>
      <button class="btn btn-sm btn-success">Tạo</button>
    </form>
  </div>
  <ul class="list-group mt-3">
    {% for c in chibos %}
      <li class="list-group-item d-flex justify-content-between align-items-center">
        {{ c.name }}
        <div>
          <a class="btn btn-sm btn-outline-primary me-1" href="{{ url_for('chi_bo_members', chi_bo_id=c.id) }}">Thành viên</a>
          <form method="post" action="{{ url_for('chi_bo_delete', chi_bo_id=c.id) }}" style="display:inline"><button class="btn btn-sm btn-outline-danger" onclick="return confirm('Xóa?')">Xóa</button></form>
        </div>
      </li>
    {% else %}
      <li class="list-group-item small text-muted">Chưa có chi bộ.</li>
    {% endfor %}
  </ul>
</div>
{% endblock %}
""",
"dang_vien_list.html": """
{% extends "base.html" %}
{% block title %}Đảng viên{% endblock %}
{% block content %}
<div class="card">
  <div class="d-flex justify-content-between">
    <h4>Đảng viên</h4>
    <form method="post" action="{{ url_for('dang_vien_create') }}" class="d-flex gap-2">
      <input name="full_name" class="form-control form-control-sm" placeholder="Họ và tên" required>
      <select name="chi_bo_id" class="form-select form-select-sm">
        <option value="">— Chi bộ —</option>
        {% for c in chibos %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}
      </select>
      <button class="btn btn-sm btn-success">Thêm</button>
    </form>
  </div>
  <table class="table mt-3">
    <thead><tr><th>#</th><th>Họ tên</th><th>Chi bộ</th><th>Hành động</th></tr></thead>
    <tbody>
      {% for m in members %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ m.full_name }}</td>
        <td>{{ m.chi_bo_name or '-' }}</td>
        <td>
          <form method="post" action="{{ url_for('dang_vien_delete', dv_id=m.id) }}" style="display:inline"><button class="btn btn-sm btn-outline-danger">Xóa</button></form>
        </td>
      </tr>
      {% else %}
      <tr><td colspan="4" class="small text-muted">Chưa có đảng viên.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
""",
"rag_chat.html": """
{% extends "base.html" %}
{% block title %}Chatbot AI{% endblock %}
{% block extra_head %}
<script>
async function apiChat(q) {
  const res = await fetch('{{ url_for("api_chat") }}', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({question: q})
  });
  return res.json();
}
function addMsg(html, cls) {
  const box = document.getElementById('chat_window');
  const div = document.createElement('div');
  div.className = cls + ' p-2 mb-2';
  div.innerHTML = html;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}
async function sendQuestion() {
  const q = document.getElementById('question').value.trim();
  if(!q) return;
  addMsg('<strong>Bạn:</strong> '+q, 'text-end');
  document.getElementById('question').value='';
  addMsg('<em>Đang xử lý...</em>', 'text-start text-muted');
  const data = await apiChat(q);
  // remove last loading
  const box = document.getElementById('chat_window');
  if (box.lastChild && box.lastChild.textContent.includes('Đang xử lý')) box.removeChild(box.lastChild);
  addMsg('<strong>Bot:</strong> '+(data.answer || data.error || 'Không có phản hồi'), 'text-start');
  if(data.source) addMsg('<div class="small text-muted">Nguồn: '+data.source+'</div>', 'text-start');
}
</script>
{% endblock %}
{% block content %}
<div class="card">
  <h5>Chatbot AI (RAG + Chat)</h5>
  <div class="row">
    <div class="col-md-8">
      <div id="chat_window" style="height:360px;overflow:auto;background:#fff;border:1px solid #e8eef0;padding:12px;border-radius:8px"></div>
      <div class="d-flex mt-2">
        <input id="question" class="form-control me-2" placeholder="Nhập câu hỏi...">
        <button class="btn btn-primary" onclick="sendQuestion()">Gửi</button>
      </div>
    </div>
    <div class="col-md-4">
      <div><strong>Upload tài liệu</strong></div>
      <form id="upload_form" method="post" action="{{ url_for('upload_file') }}" enctype="multipart/form-data">
        <input type="file" name="file" class="form-control mt-2" required>
        <button class="btn btn-success mt-2">Upload & Nhúng</button>
      </form>
      <hr>
      <div><strong>Tài liệu</strong></div>
      <div id="doc_list" class="mt-2">
        {% for d in docs %}
          <div class="small"><a href="{{ url_for('uploaded_file', filename=d.filename) }}">{{ d.filename }}</a> — {{ d.created_at }}</div>
        {% else %}
          <div class="small text-muted">Chưa có tài liệu.</div>
        {% endfor %}
      </div>
    </div>
  </div>
</div>
{% endblock %}
""",
}

# --- Jinja environment that can render our embedded templates ---
jinja_env = Environment(
    loader=DictLoader(TEMPLATES),
    autoescape=select_autoescape(['html', 'xml'])
)
# expose flask helpers
jinja_env.globals.update({
    'url_for': url_for,
    'len': len,
})

def render_template(name, **context):
    # inject current user and flash messages
    context.setdefault('user', session.get('user'))
    template = jinja_env.get_template(name)
    return template.render(**context)

# --- Database (sqlite3) ---
def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_conn()
    c = conn.cursor()
    # users table (demo)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        full_name TEXT,
        role TEXT
    )""")
    # chibos
    c.execute("""
    CREATE TABLE IF NOT EXISTS chibos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT
    )""")
    # dangvien
    c.execute("""
    CREATE TABLE IF NOT EXISTS dangvien (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT,
        email TEXT,
        chi_bo_id INTEGER
    )""")
    # rag documents
    c.execute("""
    CREATE TABLE IF NOT EXISTS rag_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        text TEXT,
        embedding TEXT,
        created_at TEXT
    )""")
    # create demo admin if not exists
    c.execute("INSERT OR IGNORE INTO users (id, username, password, full_name, role) VALUES (1,'admin','admin','Administrator','admin')")
    c.execute("INSERT OR IGNORE INTO users (id, username, password, full_name, role) VALUES (2,'user_demo','user123','User Demo','user')")
    conn.commit()
    conn.close()

init_db()

# --- Helpers for file text extraction ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def extract_text_from_pdf(fstream):
    if not PDF_AVAILABLE:
        return ""
    try:
        reader = PyPDF2.PdfReader(fstream)
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(pages)
    except Exception as e:
        print("PDF parse error:", e)
        return ""

def extract_text_from_docx(path_or_stream):
    if not DOCX_AVAILABLE:
        return ""
    try:
        # docx.Document can accept a file-like object
        doc = docx.Document(path_or_stream)
        paragraphs = [p.text for p in doc.paragraphs]
        return "\n".join(paragraphs)
    except Exception as e:
        print("DOCX parse error:", e)
        return ""

def extract_text_from_spreadsheet(path_or_stream, ext):
    # supports csv and xlsx
    try:
        if ext == "csv":
            if PANDAS_AVAILABLE:
                df = pd.read_csv(path_or_stream, dtype=str, encoding='utf-8', errors='ignore')
                return df.fillna('').to_csv(index=False)
            else:
                return path_or_stream.read().decode('utf-8', errors='ignore')
        elif ext == "xlsx":
            if PANDAS_AVAILABLE:
                df = pd.read_excel(path_or_stream, engine='openpyxl', dtype=str)
                return df.fillna('').to_csv(index=False)
    except Exception as e:
        print("Spreadsheet parse error:", e)
    return ""

# --- OpenAI helpers (embeddings + chat) ---
def create_embedding(text):
    """Return embedding as list (float) or None if not available."""
    if not (OPENAI_AVAILABLE and OPENAI_API_KEY):
        # deterministic fallback: hashed pseudo-embedding
        rng = np.random.RandomState(abs(hash(text)) % (2**32))
        return rng.normal(size=(256,)).astype(float).tolist()
    try:
        # Using text-embedding-3-small or text-embedding-3? adjust if necessary
        resp = openai.Embedding.create(input=text[:2000], model="text-embedding-3-small")
        vec = resp["data"][0]["embedding"]
        return vec
    except Exception as e:
        print("Embedding error:", e)
        return None

def chat_with_openai(system_prompt, user_prompt, max_tokens=500):
    if not (OPENAI_AVAILABLE and OPENAI_API_KEY):
        # fallback canned reply
        return "Tôi chưa kết nối OpenAI. Đây là phản hồi demo dựa trên ngữ cảnh ngắn."
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini" if hasattr(openai, "ChatCompletion") else "gpt-3.5-turbo",
            messages=[
                {"role":"system","content": system_prompt},
                {"role":"user","content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("Chat error:", e)
        # try older API path or return error text
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system","content": system_prompt},
                    {"role":"user","content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.2
            )
            return resp.choices[0].message.content.strip()
        except Exception as e2:
            print("Chat fallback error:", e2)
            return f"[Lỗi Chat] {e2}"

def cosine_sim(a, b):
    try:
        a = np.array(a, dtype=float)
        b = np.array(b, dtype=float)
        if np.linalg.norm(a)==0 or np.linalg.norm(b)==0:
            return -1.0
        return float(np.dot(a, b) / (np.linalg.norm(a)*np.linalg.norm(b)))
    except Exception:
        return -1.0

# --- Routes ---
@app.context_processor
def inject_user():
    return {"user": session.get("user")}

@app.route("/")
def index():
    if not session.get("user"):
        return redirect(url_for("login"))
    # admin goes to admin_index
    return redirect(url_for("admin_index"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT id, username, full_name, role FROM users WHERE username=? AND password=?", (username, password))
        row = c.fetchone()
        conn.close()
        if row:
            session["user"] = {"id": row["id"], "username": row["username"], "full_name": row["full_name"], "role": row["role"]}
            flash("Đăng nhập thành công", "success")
            return redirect(url_for("admin_index"))
        flash("Sai username hoặc password", "danger")
    return make_response(render_template("login.html"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/admin")
def admin_index():
    if not session.get("user"):
        return redirect(url_for("login"))
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM chibos"); chibo_count = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM dangvien"); dv_count = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM rag_documents"); doc_count = c.fetchone()["cnt"]
    conn.close()
    stats = {"chibo_count": chibo_count, "dv_count": dv_count, "doc_count": doc_count}
    return make_response(render_template("admin_dashboard.html", stats=stats, user=session.get("user")))

# Admin user management (demo in sqlite users table)
@app.route("/admin/users", methods=["GET"])
def admin_user_list():
    if not session.get("user") or session["user"].get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT id, username, full_name, role FROM users")
    rows = c.fetchall()
    conn.close()
    users = [dict(r) for r in rows]
    return make_response(render_template("admin_users.html", users=users))

@app.route("/admin/users/add", methods=["POST"])
def admin_user_add():
    if not session.get("user") or session["user"].get("role") != "admin":
        return redirect(url_for("login"))
    username = (request.form.get("username") or "").strip()
    full_name = (request.form.get("full_name") or "").strip()
    password = (request.form.get("password") or "").strip()
    if not username or not password:
        flash("Thiếu thông tin", "danger"); return redirect(url_for("admin_user_list"))
    conn = get_db_conn(); c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, full_name, role) VALUES (?,?,?,?)", (username, password, full_name, "user"))
        conn.commit(); flash("Thêm user thành công", "success")
    except Exception as e:
        flash("Lỗi: "+str(e), "danger")
    conn.close()
    return redirect(url_for("admin_user_list"))

@app.route("/admin/users/delete/<username>", methods=["POST"])
def admin_user_delete(username):
    if not session.get("user") or session["user"].get("role") != "admin":
        return redirect(url_for("login"))
    if username == "admin":
        flash("Không thể xóa admin", "danger"); return redirect(url_for("admin_user_list"))
    conn = get_db_conn(); c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit(); conn.close()
    flash("Xóa thành công", "success")
    return redirect(url_for("admin_user_list"))

# Chi bo routes
@app.route("/chi_bo", methods=["GET"])
def chi_bo_list():
    if not session.get("user"):
        return redirect(url_for("login"))
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT * FROM chibos ORDER BY name")
    rows = c.fetchall(); conn.close()
    chibos = [dict(r) for r in rows]
    return make_response(render_template("chi_bo_list.html", chibos=chibos))

@app.route("/chi_bo", methods=["POST"])
def chi_bo_create():
    if not session.get("user") or session["user"].get("role") != "admin":
        return redirect(url_for("login"))
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Tên chi bộ required", "danger"); return redirect(url_for("chi_bo_list"))
    conn = get_db_conn(); c = conn.cursor()
    try:
        c.execute("INSERT INTO chibos (name) VALUES (?)", (name,))
        conn.commit(); flash("Tạo chi bộ thành công", "success")
    except Exception as e:
        flash("Lỗi: "+str(e), "danger")
    conn.close()
    return redirect(url_for("chi_bo_list"))

@app.route("/chi_bo/<int:chi_bo_id>/members")
def chi_bo_members(chi_bo_id):
    if not session.get("user"):
        return redirect(url_for("login"))
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT * FROM chibos WHERE id=?", (chi_bo_id,)); chi = c.fetchone()
    c.execute("SELECT d.*, c.name as chi_name FROM dangvien d LEFT JOIN chibos c ON d.chi_bo_id = c.id WHERE d.chi_bo_id=?", (chi_bo_id,))
    members = [dict(r) for r in c.fetchall()]
    conn.close()
    # simple list render using dang_vien_list template for simplicity
    return make_response(render_template("dang_vien_list.html", members=members, chibos=[dict(chi) if chi else None]))

# Dang vien
@app.route("/dang_vien", methods=["GET"])
def dang_vien_list():
    if not session.get("user"):
        return redirect(url_for("login"))
    conn = get_db_conn(); c = conn.cursor()
    c.execute("""SELECT d.id, d.full_name, d.email, d.chi_bo_id, c.name as chi_bo_name
                 FROM dangvien d LEFT JOIN chibos c ON d.chi_bo_id=c.id ORDER BY d.full_name""")
    members = [dict(r) for r in c.fetchall()]
    c.execute("SELECT * FROM chibos ORDER BY name"); chibos = [dict(r) for r in c.fetchall()]
    conn.close()
    return make_response(render_template("dang_vien_list.html", members=members, chibos=chibos))

@app.route("/dang_vien", methods=["POST"])
def dang_vien_create():
    if not session.get("user") or session["user"].get("role") != "admin":
        return redirect(url_for("login"))
    full_name = (request.form.get("full_name") or "").strip()
    chi_bo_id = request.form.get("chi_bo_id") or None
    conn = get_db_conn(); c = conn.cursor()
    c.execute("INSERT INTO dangvien (full_name, email, chi_bo_id) VALUES (?,?,?)", (full_name, None, chi_bo_id))
    conn.commit(); conn.close()
    flash("Thêm đảng viên thành công", "success")
    return redirect(url_for("dang_vien_list"))

@app.route("/dang_vien/<int:dv_id>/delete", methods=["POST"])
def dang_vien_delete(dv_id):
    if not session.get("user") or session["user"].get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db_conn(); c = conn.cursor(); c.execute("DELETE FROM dangvien WHERE id=?", (dv_id,)); conn.commit(); conn.close()
    flash("Xóa thành công", "success")
    return redirect(url_for("dang_vien_list"))

# Upload & RAG
@app.route("/upload", methods=["GET"])
def upload_page():
    if not session.get("user"):
        return redirect(url_for("login"))
    return make_response(render_template("rag_chat.html", docs=get_docs_for_render()))

def get_docs_for_render():
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT filename, created_at FROM rag_documents ORDER BY created_at DESC")
    docs = [dict(r) for r in c.fetchall()]; conn.close()
    return docs

@app.route("/upload", methods=["POST"])
def upload_file():
    if not session.get("user"):
        return jsonify({"error":"Unauthorized"}), 403
    f = request.files.get("file")
    if not f:
        return jsonify({"error":"No file"}), 400
    filename = secure_filename(f.filename)
    if not allowed_file(filename):
        return jsonify({"error":"File type not allowed"}), 400
    ext = filename.rsplit(".",1)[1].lower()
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    # ensure unique filename
    base, dot, tail = filename.partition(".")
    idx = 1
    while os.path.exists(save_path):
        filename = f"{base}_{idx}.{tail}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        idx += 1
    f.stream.seek(0)
    f.save(save_path)
    # extract text
    f.stream.seek(0)
    text = ""
    try:
        if ext == "pdf":
            with open(save_path, "rb") as fh:
                text = extract_text_from_pdf(fh)
        elif ext == "docx":
            with open(save_path, "rb") as fh:
                text = extract_text_from_docx(fh)
        elif ext in ("csv", "xlsx"):
            if PANDAS_AVAILABLE:
                with open(save_path, "rb") as fh:
                    text = extract_text_from_spreadsheet(save_path if ext=="xlsx" else fh, ext)
            else:
                text = ""
        else:
            # txt, md
            try:
                with open(save_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except:
                with open(save_path, "r", encoding="latin-1", errors="ignore") as fh:
                    text = fh.read()
    except Exception as e:
        print("Extract error:", e)
        text = ""
    text_short = (text[:4000] + "...") if text and len(text) > 4000 else (text or "")
    # create embedding (maybe None)
    embedding = None
    try:
        embedding = create_embedding(text_short or filename)
    except Exception as e:
        print("Embedding create failed:", e)
        embedding = None
    emb_json = json.dumps(embedding) if embedding is not None else None
    # persist to DB
    conn = get_db_conn(); c = conn.cursor()
    c.execute("INSERT INTO rag_documents (filename, text, embedding, created_at) VALUES (?,?,?,?)",
              (filename, text, emb_json, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()
    return redirect(url_for("upload_page"))

@app.route("/docs/list")
def list_docs():
    if not session.get("user"):
        return jsonify([]), 403
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT id, filename, created_at FROM rag_documents ORDER BY created_at DESC")
    out = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(out)

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=False)

# API chat - RAG + Chat
@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not session.get("user"):
        return jsonify({"error":"Unauthorized"}), 403
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error":"Empty question"}), 400
    # compute question embedding
    q_emb = create_embedding(question)
    # load docs and compute similarity
    conn = get_db_conn(); c = conn.cursor()
    c.execute("SELECT id, filename, text, embedding FROM rag_documents")
    docs = []
    for r in c.fetchall():
        emb = None
        if r["embedding"]:
            try:
                emb = json.loads(r["embedding"])
            except Exception:
                emb = None
        docs.append({"id": r["id"], "filename": r["filename"], "text": r["text"], "embedding": emb})
    conn.close()
    sims = []
    if q_emb is not None:
        for d in docs:
            if d["embedding"]:
                s = cosine_sim(q_emb, d["embedding"])
                sims.append((s, d))
        sims.sort(key=lambda x: x[0], reverse=True)
    # choose top sources with positive similarity or fallback
    top_docs = [d for s,d in sims[:3] if s > 0.0] if sims else []
    context = "\n\n".join([td["text"][:1500] for td in top_docs]) if top_docs else ""
    # compose prompt
    system_prompt = "Bạn là trợ lý hữu ích, trả lời ngắn gọn bằng tiếng Việt. Nếu có thể, dựa vào ngữ cảnh tài liệu đã upload trước đó để trả lời."
    user_prompt = f"Ngữ cảnh:\n{context}\n\nCâu hỏi: {question}\n\nTrả lời ngắn gọn, rõ ràng."
    answer = chat_with_openai(system_prompt, user_prompt, max_tokens=400)
    source_list = ", ".join([d["filename"] for d in top_docs]) if top_docs else ""
    return jsonify({"answer": answer, "source": source_list})

# error handler
@app.errorhandler(500)
def internal_error(e):
    return f"Internal Server Error: {e}", 500

# Run
if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("RENDER_PORT", 5000)))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
