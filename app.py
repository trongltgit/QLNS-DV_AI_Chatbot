# app.py - Single-file Flask app (templates embedded)
# Features:
# - Auth (SQLite)
# - Chi bộ, Đảng viên, Sinh hoạt
# - Upload files (pdf, docx, xlsx, csv, txt)
# - Extract text, store docs, summary (OpenAI optional)
# - RAG chat (simple embedding fallback)
# - Uses Jinja2 DictLoader to avoid TemplateNotFound

import os
import io
import sqlite3
import json
import traceback
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, session, redirect, url_for, flash,
    jsonify, send_from_directory, Response
)

# templating
from jinja2 import Environment, DictLoader, select_autoescape

# file handling / parsing
from werkzeug.utils import secure_filename

# optional heavy libs
try:
    import numpy as np
except Exception:
    np = None

try:
    import PyPDF2
    PDF_AVAILABLE = True
except Exception:
    PyPDF2 = None
    PDF_AVAILABLE = False

try:
    import docx   # python-docx
    DOCX_AVAILABLE = True
except Exception:
    docx = None
    DOCX_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False

# optional embedding model
DISABLE_EMBEDDING = os.environ.get("DISABLE_EMBEDDING", "0") == "1"
EMBED_MODEL = None
try:
    if not DISABLE_EMBEDDING:
        from sentence_transformers import SentenceTransformer
        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        EMBED_AVAILABLE = True
    else:
        EMBED_AVAILABLE = False
except Exception:
    EMBED_AVAILABLE = False
    EMBED_MODEL = None

# optional OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
try:
    import openai
    OPENAI_AVAILABLE = True
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
except Exception:
    openai = None
    OPENAI_AVAILABLE = False

# config
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")
DB_PATH = os.environ.get("DB_PATH", "app_singlefile.db")
ALLOWED_EXT = {"pdf", "docx", "xlsx", "csv", "txt", "md"}
SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_2025")
PORT = int(os.environ.get("PORT", 10000))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------------------------
# Templates (DictLoader)
# ---------------------------
TEMPLATES = {
"base.html": """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}QLNS - Đảng viên{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    :root{--primary:#0B6E3B;--accent:#3AA14A}
    body{background:#f4f6f8}
    header{background:#fff;padding:12px;border-bottom:1px solid #e6eaed}
    .brand{display:flex;gap:12px;align-items:center}
    .card-inner{padding:16px;background:#fff;border-radius:8px}
  </style>
  {% block head %}{% endblock %}
</head>
<body>
  <header class="container d-flex justify-content-between align-items-center">
    <div class="brand">
      <div style="width:56px;height:56px;border-radius:8px;background:var(--primary);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">LTT</div>
      <div>
        <h4 style="margin:0;color:var(--primary)">HỆ THỐNG QLNS - ĐẢNG VIÊN</h4>
        <small class="text-muted">Chatbot AI & Quản lý Sinh hoạt</small>
      </div>
    </div>
    <div>
      {% if user %}
        <div class="text-end">
          <div style="font-weight:600;color:var(--accent)">{{ user.full_name or user.username }}</div>
          <div class="small text-muted">{{ user.role|upper }}</div>
          <a href="{{ url_for('logout') }}" class="btn btn-sm btn-outline-secondary mt-1">Đăng xuất</a>
        </div>
      {% else %}
        <a href="{{ url_for('login') }}" class="btn btn-sm btn-outline-primary">Đăng nhập</a>
      {% endif %}
    </div>
  </header>

  {% if user %}
  <nav class="bg-success text-white py-2">
    <div class="container d-flex gap-3">
      <a class="text-white" href="{{ url_for('admin_dashboard') }}">Dashboard</a>
      <a class="text-white" href="{{ url_for('chi_bo_list') }}">Chi bộ</a>
      <a class="text-white" href="{{ url_for('dang_vien_list') }}">Đảng viên</a>
      <a class="text-white" href="{{ url_for('upload_page') }}">Upload</a>
      <a class="text-white" href="{{ url_for('rag_chat') }}">Chatbot</a>
    </div>
  </nav>
  {% endif %}

  <main class="container my-4">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat,msg in messages %}
          <div class="alert alert-{{ cat if cat else 'info' }}">{{ msg }}</div>
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
<div class="row justify-content-center">
  <div class="col-md-5">
    <div class="card-inner">
      <h4>Đăng nhập</h4>
      <form method="post">
        <div class="mb-2">
          <input name="username" class="form-control" placeholder="Tên đăng nhập" required>
        </div>
        <div class="mb-2">
          <input name="password" class="form-control" type="password" placeholder="Mật khẩu" required>
        </div>
        <div class="d-flex justify-content-between">
          <button class="btn btn-success">Đăng nhập</button>
          <a href="#" class="btn btn-link" onclick="alert('Demo user: admin/admin')">?</a>
        </div>
      </form>
    </div>
  </div>
</div>
{% endblock %}
""",

"admin_dashboard.html": """
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<div class="card-inner">
  <h4>Xin chào {{ user.full_name or user.username }}</h4>
  <p class="small text-muted">Số chi bộ: {{ stats.chibos }} — Số đảng viên: {{ stats.dangviens }} — Số tài liệu: {{ stats.docs }}</p>
  <div class="mt-3">
    <a class="btn btn-primary" href="{{ url_for('chi_bo_list') }}">Quản lý Chi bộ</a>
    <a class="btn btn-primary" href="{{ url_for('dang_vien_list') }}">Quản lý Đảng viên</a>
    <a class="btn btn-success" href="{{ url_for('upload_page') }}">Upload tài liệu</a>
    <a class="btn btn-secondary" href="{{ url_for('rag_chat') }}">Chatbot RAG</a>
  </div>
</div>
{% endblock %}
""",

"chi_bo_list.html": """
{% extends "base.html" %}
{% block title %}Chi bộ{% endblock %}
{% block content %}
<div class="card-inner">
  <div class="d-flex justify-content-between align-items-center">
    <h5>Danh sách Chi bộ</h5>
    <form method="post" action="{{ url_for('chi_bo_create') }}" class="d-flex gap-2">
      <input name="name" class="form-control form-control-sm" placeholder="Tên chi bộ" required>
      <button class="btn btn-sm btn-success">Tạo</button>
    </form>
  </div>
  <hr>
  {% if chibos %}
    <ul class="list-group">
      {% for c in chibos %}
        <li class="list-group-item d-flex justify-content-between align-items-center">
          {{ c.name }}
          <div>
            <a class="btn btn-sm btn-outline-primary" href="{{ url_for('chi_bo_detail', chi_bo_id=c.id) }}">Chi tiết</a>
            <form method="post" action="{{ url_for('chi_bo_delete', chi_bo_id=c.id) }}" style="display:inline">
              <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Xóa?')">Xóa</button>
            </form>
          </div>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <div class="text-muted">Chưa có chi bộ.</div>
  {% endif %}
</div>
{% endblock %}
""",

"chi_bo_detail.html": """
{% extends "base.html" %}
{% block title %}Chi bộ{% endblock %}
{% block content %}
<div class="card-inner">
  <h5>Chi bộ: {{ chi_bo.name }}</h5>
  <h6 class="mt-3">Thành viên</h6>
  {% if members %}
    <table class="table table-sm">
      <thead><tr><th>#</th><th>Họ tên</th><th>Email</th></tr></thead>
      <tbody>
        {% for m in members %}
          <tr><td>{{ loop.index }}</td><td>{{ m.full_name }}</td><td>{{ m.email or '-' }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <div class="text-muted">Chưa có đảng viên trong chi bộ này.</div>
  {% endif %}
</div>
{% endblock %}
""",

"dang_vien_list.html": """
{% extends "base.html" %}
{% block title %}Đảng viên{% endblock %}
{% block content %}
<div class="card-inner">
  <div class="d-flex justify-content-between align-items-center">
    <h5>Đảng viên</h5>
    <form method="post" action="{{ url_for('dang_vien_create') }}" class="d-flex gap-2">
      <input name="full_name" class="form-control form-control-sm" placeholder="Họ và tên" required>
      <select name="chi_bo_id" class="form-select form-select-sm">
        <option value="">— Chi bộ —</option>
        {% for c in chibos %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}
      </select>
      <button class="btn btn-sm btn-success">Thêm</button>
    </form>
  </div>
  <hr>
  <table class="table table-striped">
    <thead><tr><th>#</th><th>Họ tên</th><th>Email</th><th>Chi bộ</th></tr></thead>
    <tbody>
      {% for m in members %}
        <tr><td>{{ loop.index }}</td><td>{{ m.full_name }}</td><td>{{ m.email or '-' }}</td><td>{{ m.chi_bo_name or '-' }}</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
""",

"upload.html": """
{% extends "base.html" %}
{% block title %}Upload tài liệu{% endblock %}
{% block content %}
<div class="card-inner">
  <h5>Upload tài liệu</h5>
  <form method="post" enctype="multipart/form-data" action="{{ url_for('upload_file') }}">
    <div class="mb-2">
      <input type="file" name="file" class="form-control" required>
    </div>
    <div class="mb-2">
      <select name="doc_type" class="form-select">
        <option value="general">Tài liệu chung</option>
      </select>
    </div>
    <button class="btn btn-success">Upload & Nhúng</button>
  </form>
  <hr>
  <h6>Danh sách tài liệu</h6>
  {% if docs %}
    <ul class="list-group">
      {% for d in docs %}
        <li class="list-group-item d-flex justify-content-between">
          <div>
            <strong>{{ d.filename }}</strong><br><small class="text-muted">{{ d.filetype }} — {{ d.uploaded_at }}</small>
          </div>
          <div>
            <a class="btn btn-sm btn-outline-primary" href="{{ url_for('download_file', filename=d.filepath) }}">Tải</a>
            <form method="post" action="{{ url_for('delete_doc', doc_id=d.id) }}" style="display:inline">
              <button class="btn btn-sm btn-outline-danger" onclick="return confirm('Xóa tài liệu?')">Xóa</button>
            </form>
          </div>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <div class="text-muted">Chưa có tài liệu.</div>
  {% endif %}
</div>
{% endblock %}
""",

"rag_chat.html": """
{% extends "base.html" %}
{% block title %}Chatbot RAG{% endblock %}
{% block scripts %}
<script>
async function ask() {
  const q = document.getElementById('q').value.trim();
  if(!q) return;
  const res = await fetch('{{ url_for("api_chat") }}', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({question: q})
  });
  const data = await res.json();
  document.getElementById('answer').innerText = data.answer || data.error || 'No answer';
  document.getElementById('source').innerText = data.source || '';
}
</script>
{% endblock %}
{% block content %}
<div class="card-inner">
  <h5>Chatbot RAG</h5>
  <div class="mb-2">
    <input id="q" class="form-control" placeholder="Hỏi về tài liệu..." />
  </div>
  <div class="mb-2">
    <button class="btn btn-primary" onclick="ask()">Gửi</button>
  </div>
  <h6>Trả lời</h6>
  <pre id="answer" style="white-space:pre-wrap;"></pre>
  <div class="small text-muted">Nguồn: <span id="source"></span></div>
</div>
{% endblock %}
"""
}

# Setup Jinja2 environment with DictLoader
jinja_env = Environment(
    loader=DictLoader(TEMPLATES),
    autoescape=select_autoescape(['html','xml'])
)

def render_template_name(name, **context):
    """Render template from TEMPLATES dict via Jinja2 Environment."""
    # inject 'user' from session
    user = session.get("user")
    context.setdefault("user", user)
    template = jinja_env.get_template(name)
    return template.render(**context)

# ---------------------------
# DB helpers (SQLite)
# ---------------------------
def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_conn()
    c = conn.cursor()
    # chi bo
    c.execute("""
    CREATE TABLE IF NOT EXISTS chi_bo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        description TEXT,
        created_at TEXT
    )""")
    # dang vien
    c.execute("""
    CREATE TABLE IF NOT EXISTS dang_vien (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        full_name TEXT,
        username TEXT UNIQUE,
        email TEXT,
        chi_bo_id INTEGER,
        created_at TEXT
    )""")
    # sinh hoat
    c.execute("""
    CREATE TABLE IF NOT EXISTS sinh_hoat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chi_bo_id INTEGER,
        ngay_sinh_hoat TEXT,
        tieu_de TEXT,
        noi_dung TEXT,
        ghi_chu TEXT,
        created_at TEXT
    )""")
    # documents
    c.execute("""
    CREATE TABLE IF NOT EXISTS docs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        filepath TEXT,
        filetype TEXT,
        text_content TEXT,
        summary TEXT,
        embedding_blob BLOB,
        uploaded_by TEXT,
        uploaded_at TEXT
    )""")
    # users (simple demo users)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        full_name TEXT
    )""")
    # create default admin if not exists
    c.execute("INSERT OR IGNORE INTO users (username,password,role,full_name) VALUES (?,?,?,?)",
              ("admin", "admin", "admin", "Administrator"))
    conn.commit()
    conn.close()

init_db()

# ---------------------------
# Auth / decorators
# ---------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        u = session.get("user")
        if not u or u.get("role") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# ---------------------------
# Utilities: file parsing, embedding, summarization
# ---------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXT

def read_pdf(stream):
    if not PDF_AVAILABLE:
        return ""
    try:
        reader = PyPDF2.PdfReader(stream)
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n\n".join(pages)
    except Exception as e:
        print("pdf read error:", e)
        return ""

def read_docx(stream):
    if not DOCX_AVAILABLE:
        return ""
    try:
        # python-docx expects a filename or file-like (BytesIO works)
        bio = io.BytesIO(stream.read())
        doc = docx.Document(bio)
        ps = []
        for p in doc.paragraphs:
            ps.append(p.text)
        return "\n".join(ps)
    except Exception as e:
        print("docx read error:", e)
        return ""

def read_table_file(stream, ext):
    if not PANDAS_AVAILABLE:
        return ""
    try:
        if ext == "csv":
            df = pd.read_csv(stream)
        else:
            # xlsx
            df = pd.read_excel(stream, engine="openpyxl")
        # convert to text summary
        return df.to_csv(index=False)
    except Exception as e:
        print("table read error:", e)
        return ""

def read_text(stream):
    try:
        data = stream.read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="ignore")
        return str(data)
    except Exception as e:
        print("text read error:", e)
        return ""

def embed_text(text):
    """Return numpy vector bytes or deterministic fallback bytes."""
    if not np:
        return None
    try:
        if EMBED_AVAILABLE and EMBED_MODEL:
            vec = EMBED_MODEL.encode(text, convert_to_numpy=True)
        else:
            # deterministic pseudo-random vector
            rng = np.random.RandomState(abs(hash(text)) % (2**32))
            vec = rng.normal(size=(384,))
        # return binary
        bio = io.BytesIO()
        np.save(bio, np.asarray(vec, dtype=np.float32), allow_pickle=False)
        bio.seek(0)
        return bio.read()
    except Exception as e:
        print("embed error:", e)
        return None

def bytes_to_vector(b):
    if not b or not np:
        return None
    try:
        bio = io.BytesIO(b)
        bio.seek(0)
        arr = np.load(bio, allow_pickle=False)
        return arr
    except Exception:
        return None

def cosine_sim(a,b):
    try:
        if a is None or b is None:
            return -1.0
        a_norm = a / (np.linalg.norm(a) + 1e-12)
        b_norm = b / (np.linalg.norm(b) + 1e-12)
        return float(np.dot(a_norm, b_norm))
    except Exception:
        return -1.0

def summarize_text(text, max_tokens=200):
    """Use OpenAI if available, else simple heuristic summary (first 400 chars)."""
    if not text:
        return ""
    if OPENAI_AVAILABLE and OPENAI_API_KEY:
        try:
            prompt = f"Tóm tắt ngắn bằng tiếng Việt, tối đa 150 từ:\n\n{text[:3000]}"
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system", "content":"Bạn là trợ lý hữu ích, viết bằng tiếng Việt."},
                    {"role":"user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.2
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print("openai summary error:", e)
    # fallback
    s = text.strip().replace("\n"," ")
    if len(s) <= 800:
        return s
    return s[:800].rsplit(" ",1)[0] + " ..."

# ---------------------------
# Routes
# ---------------------------
@app.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        row = c.fetchone()
        conn.close()
        if row:
            user = {"id": row["id"], "username": row["username"], "role": row["role"], "full_name": row["full_name"]}
            session["user"] = user
            flash("Đăng nhập thành công", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Sai tên đăng nhập hoặc mật khẩu", "danger")
    return render_template_name("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin_dashboard():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM chi_bo"); chibos = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) AS cnt FROM dang_vien"); dv = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) AS cnt FROM docs"); docs = c.fetchone()["cnt"]
    conn.close()
    stats = {"chibos": chibos, "dangviens": dv, "docs": docs}
    return render_template_name("admin_dashboard.html", stats=stats)

# ---------- Chi bo ----------
@app.route("/chi_bo", methods=["GET"])
@login_required
def chi_bo_list():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM chi_bo ORDER BY name ASC")
    rows = c.fetchall()
    chibos = [dict(id=r["id"], name=r["name"], description=r["description"]) for r in rows]
    conn.close()
    return render_template_name("chi_bo_list.html", chibos=chibos)

@app.route("/chi_bo/create", methods=["POST"])
@admin_required
def chi_bo_create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Tên chi bộ required", "danger")
        return redirect(url_for("chi_bo_list"))
    conn = get_db_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO chi_bo (name, description, created_at) VALUES (?,?,?)",
                  (name, "", datetime.utcnow().isoformat()))
        conn.commit()
        flash("Tạo chi bộ thành công", "success")
    except sqlite3.IntegrityError:
        flash("Chi bộ đã tồn tại", "danger")
    conn.close()
    return redirect(url_for("chi_bo_list"))

@app.route("/chi_bo/<int:chi_bo_id>", methods=["GET"])
@login_required
def chi_bo_detail(chi_bo_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM chi_bo WHERE id=?", (chi_bo_id,))
    chi = c.fetchone()
    if not chi:
        conn.close()
        flash("Chi bộ không tồn tại", "danger")
        return redirect(url_for("chi_bo_list"))
    c.execute("SELECT * FROM dang_vien WHERE chi_bo_id=?", (chi_bo_id,))
    members = [dict(id=r["id"], full_name=r["full_name"], email=r["email"]) for r in c.fetchall()]
    conn.close()
    return render_template_name("chi_bo_detail.html", chi_bo=dict(id=chi["id"], name=chi["name"]), members=members)

@app.route("/chi_bo/<int:chi_bo_id>/delete", methods=["POST"])
@admin_required
def chi_bo_delete(chi_bo_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("DELETE FROM chi_bo WHERE id=?", (chi_bo_id,))
    conn.commit()
    conn.close()
    flash("Đã xóa chi bộ", "success")
    return redirect(url_for("chi_bo_list"))

# ---------- Dang vien ----------
@app.route("/dang_vien", methods=["GET"])
@login_required
def dang_vien_list():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
      SELECT dv.*, cb.name AS chi_bo_name FROM dang_vien dv
      LEFT JOIN chi_bo cb ON dv.chi_bo_id = cb.id
      ORDER BY dv.full_name
    """)
    members = [dict(id=r["id"], full_name=r["full_name"], email=r["email"], chi_bo_name=r["chi_bo_name"]) for r in c.fetchall()]
    c.execute("SELECT * FROM chi_bo ORDER BY name")
    chibos = [dict(id=r["id"], name=r["name"]) for r in c.fetchall()]
    conn.close()
    return render_template_name("dang_vien_list.html", members=members, chibos=chibos)

@app.route("/dang_vien/create", methods=["POST"])
@admin_required
def dang_vien_create():
    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    chi_bo_id = request.form.get("chi_bo_id") or None
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO dang_vien (full_name, email, chi_bo_id, created_at) VALUES (?,?,?,?)",
              (full_name, email or None, chi_bo_id if chi_bo_id else None, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    flash("Thêm đảng viên thành công", "success")
    return redirect(url_for("dang_vien_list"))

# ---------- Upload & Docs ----------
@app.route("/upload", methods=["GET"])
@login_required
def upload_page():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM docs ORDER BY uploaded_at DESC")
    docs = [dict(id=r["id"], filename=r["filename"], filepath=r["filepath"], filetype=r["filetype"], uploaded_at=r["uploaded_at"]) for r in c.fetchall()]
    conn.close()
    return render_template_name("upload.html", docs=docs)

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    f = request.files.get("file")
    if not f:
        flash("Chưa chọn file", "danger")
        return redirect(url_for("upload_page"))
    filename = secure_filename(f.filename)
    if not allowed_file(filename):
        flash("Định dạng không được phép", "danger")
        return redirect(url_for("upload_page"))
    ext = filename.rsplit(".",1)[1].lower()
    save_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
    save_path = os.path.join(UPLOAD_FOLDER, save_name)
    f.stream.seek(0)
    f.save(save_path)
    # read content
    try:
        with open(save_path, "rb") as fh:
            if ext == "pdf":
                text = read_pdf(fh)
            elif ext == "docx":
                # reopen file as bytes for docx reader
                with open(save_path, "rb") as sf:
                    text = read_docx(sf)
            elif ext in ("csv","xlsx"):
                with open(save_path, "rb") as sf:
                    text = read_table_file(sf, ext)
            else:
                with open(save_path, "rb") as sf:
                    text = read_text(sf)
    except Exception as e:
        print("read saved file error:", e)
        text = ""
    summary = summarize_text(text)
    emb = embed_text(text) if text else None
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
      INSERT INTO docs (filename, filepath, filetype, text_content, summary, embedding_blob, uploaded_by, uploaded_at)
      VALUES (?,?,?,?,?,?,?,?)
    """, (filename, save_name, ext, text, summary, emb, session["user"]["username"], datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    flash(f"Upload thành công: {filename}", "success")
    return redirect(url_for("upload_page"))

@app.route("/docs/download/<path:filename>")
@login_required
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/docs/delete/<int:doc_id>", methods=["POST"])
@admin_required
def delete_doc(doc_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT filepath FROM docs WHERE id=?", (doc_id,))
    r = c.fetchone()
    if r:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, r["filepath"]))
        except Exception:
            pass
    c.execute("DELETE FROM docs WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()
    flash("Xóa tài liệu thành công", "success")
    return redirect(url_for("upload_page"))

# alias endpoints matching earlier names
@app.route("/download/<path:filename>")
@login_required
def download_file_alias(filename):
    return download_file(filename)

# ---------------------------
# RAG Chat API
# ---------------------------
@app.route("/rag_chat")
@login_required
def rag_chat():
    return render_template_name("rag_chat.html")

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error":"Empty question"}), 400

    # embed question
    q_emb = embed_text(question) if question else None
    q_vec = bytes_to_vector(q_emb) if q_emb else None

    # load docs embeddings and compute sim
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, filename, summary, text_content, embedding_blob FROM docs")
    docs = c.fetchall()
    scored = []
    for d in docs:
        emb_blob = d["embedding_blob"]
        if emb_blob:
            vec = bytes_to_vector(emb_blob)
            if vec is not None and q_vec is not None:
                try:
                    sim = cosine_sim(q_vec, vec)
                except Exception:
                    sim = -1.0
            else:
                sim = -1.0
        else:
            sim = -1.0
        scored.append((sim, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    # take top 3 positive sims
    top_docs = [d for s,d in scored[:3] if s > 0.0]
    context_text = "\n\n".join([(d["summary"] or d["text_content"] or "")[:1500] for d in top_docs]).strip()

    # if OpenAI available, ask model with context
    if OPENAI_AVAILABLE and OPENAI_API_KEY:
        try:
            system = "Bạn là trợ lý, trả lời ngắn gọn bằng tiếng Việt. Sử dụng ngữ cảnh nếu có."
            user_prompt = f"Ngữ cảnh:\n{context_text}\n\nCâu hỏi: {question}"
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role":"system","content":system},{"role":"user","content":user_prompt}],
                max_tokens=400,
                temperature=0.2
            )
            answer = resp.choices[0].message.content.strip()
        except Exception as e:
            print("openai chat error:", e)
            answer = "Lỗi khi gọi OpenAI. " + summarize_text(question)
    else:
        # fallback: simple rule-based answer
        if context_text:
            answer = "Dựa trên tài liệu: " + (context_text[:800] + ("..." if len(context_text)>800 else ""))
        else:
            answer = "Tôi chưa có tài liệu phù hợp. (Demo trả lời): " + (question[:300])
    source_files = ", ".join([d["filename"] for d in top_docs])
    conn.close()
    return jsonify({"answer": answer, "source": source_files})

# ---------------------------
# Additional helper routes for admin user management (simple)
# ---------------------------
@app.route("/admin/users", methods=["GET"])
@admin_required
def admin_users():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, role, full_name FROM users ORDER BY username")
    users = [dict(id=r["id"], username=r["username"], role=r["role"], full_name=r["full_name"]) for r in c.fetchall()]
    conn.close()
    return jsonify(users)

# ---------------------------
# Error handlers
# ---------------------------
@app.errorhandler(500)
def on_500(e):
    tb = traceback.format_exc()
    print("Internal error:", tb)
    return Response(f"Internal Server Error\n\n{str(e)}", status=500)

# ---------------------------
# Run app
# ---------------------------
if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=PORT, debug=debug)
