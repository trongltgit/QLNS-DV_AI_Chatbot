# app.py - Single-file Flask app (all templates embedded)
# Supports: Auth, Chi bộ, Đảng viên, Sinh hoạt, Upload docs, RAG Chat
# Designed to run on low-RAM (Render free 512MB) with embedding fallback.

import os
import io
import json
import numpy as np
from datetime import datetime
from flask import (
    Flask, render_template_string, request, redirect, session,
    flash, jsonify, url_for, send_from_directory
)
from werkzeug.utils import secure_filename

# Database (SQLAlchemy)
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean, LargeBinary
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session

# Optional heavy deps
DISABLE_EMBEDDING = (
    os.environ.get("DISABLE_EMBEDDING", "0") == "1" or
    os.environ.get("RENDER", None) is not None or
    os.environ.get("RAILWAY", None) is not None
)

try:
    if not DISABLE_EMBEDDING:
        from sentence_transformers import SentenceTransformer
    EMBED_AVAILABLE = True
except Exception as e:
    print(f"[INFO] sentence-transformers unavailable or disabled: {e}")
    EMBED_AVAILABLE = False

try:
    import PyPDF2
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# Config
UPLOAD_FOLDER = "uploads"
ALLOWED_EXT = {"txt", "pdf", "md"}
SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-key-2025")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")  # if Postgres provided on Render

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

if OPENAI_API_KEY and OPENAI_AVAILABLE:
    openai.api_key = OPENAI_API_KEY

# DB setup
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL or "sqlite:///./app_singlefile.db",
    connect_args={"check_same_thread": False} if (DATABASE_URL is None or "sqlite" in (DATABASE_URL or "")) else {},
    pool_pre_ping=True
)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()

# Models
class ChiBo(Base):
    __tablename__ = "chi_bo"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    dangviens = relationship("DangVien", back_populates="chi_bo")
    sinhhoats = relationship("SinhHoatDang", back_populates="chi_bo")

class DangVien(Base):
    __tablename__ = "dang_vien"
    id = Column(Integer, primary_key=True)
    code = Column(String)
    full_name = Column(String, nullable=False)
    username = Column(String, unique=True)
    email = Column(String)
    chi_bo_id = Column(Integer, ForeignKey("chi_bo.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    chi_bo = relationship("ChiBo", back_populates="dangviens")
    attendances = relationship("SinhHoatAttendance", back_populates="dang_vien")

class SinhHoatDang(Base):
    __tablename__ = "sinh_hoat_dang"
    id = Column(Integer, primary_key=True)
    chi_bo_id = Column(Integer, ForeignKey("chi_bo.id"), nullable=False)
    ngay_sinh_hoat = Column(DateTime, nullable=False)
    tieu_de = Column(String, nullable=False)
    noi_dung = Column(Text)
    hinh_thuc = Column(String, default="truc_tiep")
    danh_gia = Column(String)
    ghi_chu = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    chi_bo = relationship("ChiBo", back_populates="sinhhoats")
    attendances = relationship("SinhHoatAttendance", back_populates="sinh_hoat")

class SinhHoatAttendance(Base):
    __tablename__ = "sinh_hoat_attendance"
    id = Column(Integer, primary_key=True)
    sinh_hoat_id = Column(Integer, ForeignKey("sinh_hoat_dang.id"), nullable=False)
    dang_vien_id = Column(Integer, ForeignKey("dang_vien.id"), nullable=False)
    co_mat = Column(Boolean, default=False)
    ly_do_vang = Column(String)
    ghi_chu = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    sinh_hoat = relationship("SinhHoatDang", back_populates="attendances")
    dang_vien = relationship("DangVien", back_populates="attendances")

class RAGDocument(Base):
    __tablename__ = "rag_documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String)
    text = Column(Text, nullable=False)
    embedding = Column(LargeBinary)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Simple in-memory user store (for demo). Admin can add/delete/reset.
USERS = {
    "admin": {"username": "admin", "password": "Test@321", "role": "admin", "full_name": "Administrator"},
    "user_demo": {"username": "user_demo", "password": "Test@123", "role": "user", "full_name": "Người dùng Demo"},
}

# Embedding model load (if allowed)
EMBED_MODEL = None
if EMBED_AVAILABLE and not DISABLE_EMBEDDING:
    try:
        print("[INFO] Loading embedding model all-MiniLM-L6-v2 ...")
        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        print("[SUCCESS] Embedding model loaded.")
    except Exception as e:
        print(f"[WARNING] Could not load embedding model: {e}")
        EMBED_MODEL = None
else:
    print("[INFO] Embedding disabled or unavailable (using random fallback).")

# Helpers
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def extract_text_from_pdf(stream):
    if not PDF_AVAILABLE:
        return ""
    try:
        reader = PyPDF2.PdfReader(stream)
        texts = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(texts)
    except Exception as e:
        print("PDF extract error:", e)
        return ""

def embed_text(text):
    """Return numpy float32 vector; either real embed or deterministic random fallback."""
    if EMBED_MODEL:
        try:
            vec = EMBED_MODEL.encode(text, convert_to_numpy=True)
            return vec.astype(np.float32)
        except Exception as e:
            print("Embedding error:", e)
    # deterministic random fallback (so same text -> same vector)
    rng = np.random.RandomState(abs(hash(text)) % 2**32)
    return rng.normal(size=(384,)).astype(np.float32)

def numpy_to_bytes(arr):
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    buf.seek(0)
    return buf.read()

def bytes_to_numpy(b):
    buf = io.BytesIO(b)
    buf.seek(0)
    return np.load(buf, allow_pickle=False)

def cosine_sim(a, b):
    try:
        if a is None or b is None or len(a) == 0 or len(b) == 0:
            return -1.0
        a = a / np.linalg.norm(a)
        b = b / np.linalg.norm(b)
        return float(np.dot(a, b))
    except Exception:
        return -1.0

def llm_answer(prompt, max_tokens=400):
    """Call OpenAI (if available); otherwise simple fallback."""
    if OPENAI_AVAILABLE and OPENAI_API_KEY:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Bạn là trợ lý hữu ích, trả lời bằng tiếng Việt, ngắn gọn, chính xác."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.2
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[Lỗi LLM] {e}"
    # fallback heuristic: return context + short canned answer
    summary = prompt[:1500]
    return "Tôi chưa kết nối OpenAI. Dưới đây là ngữ cảnh trích xuất:\n\n" + summary[:1000] + "\n\n(Tự động trả lời demo)."

# Templates (embedded)
BASE_HTML = """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}Hệ thống QLNS - RAG Chat{% endblock %}</title>
  <style>
    :root{--primary:#0B6E3B;--accent:#3AA14A}
    body{font-family:Inter,Segoe UI,Arial;background:#f4f6f8;margin:0;color:#222}
    .container{max-width:1100px;margin:20px auto;padding:16px}
    header{background:#fff;padding:12px 16px;border-bottom:1px solid #e6eaed;display:flex;align-items:center;justify-content:space-between}
    header .brand{display:flex;gap:12px;align-items:center}
    header h1{margin:0;color:var(--primary);font-size:1.2rem}
    nav a{margin-left:10px;color:#fff;text-decoration:none}
    .navbar{background:var(--primary);padding:8px 16px;color:#fff}
    .card{background:#fff;border-radius:8px;padding:16px;box-shadow:0 2px 6px rgba(0,0,0,0.05);margin-bottom:16px}
    .btn{display:inline-block;padding:8px 12px;border-radius:6px;border:0;cursor:pointer}
    .btn-primary{background:var(--primary);color:#fff}
    .btn-success{background:var(--accent);color:#fff}
    .btn-light{background:#f1f3f5;color:#222}
    .muted{color:#68707d}
    .flex{display:flex;gap:12px;align-items:center}
    .chat-window{height:420px;overflow:auto;padding:12px;background:#fafafa;border:1px solid #eceff1;border-radius:8px}
    .msg{padding:8px 12px;border-radius:12px;margin:8px 0;display:inline-block;max-width:80%}
    .me{background:#cdeaff;margin-left:auto}
    .bot{background:#fff7e6}
    .doc-card{border:1px dashed #e0e6ea;padding:8px;border-radius:8px}
    .small{font-size:0.85rem;color:#555}
    form .row{display:flex;gap:8px}
    input[type=text], textarea{width:100%;padding:8px;border:1px solid #dfe6ea;border-radius:6px}
    @media(max-width:640px){.flex{flex-direction:column;align-items:stretch}}
  </style>
  {% block extra_head %}{% endblock %}
</head>
<body>
  <header>
    <div class="brand">
      <div style="width:56px;height:56px;border-radius:8px;background:var(--primary);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700">LTT</div>
      <div>
        <h1>HỆ THỐNG QLNS - ĐẢNG VIÊN</h1>
        <div class="small muted">Chatbot AI & Quản lý Sinh hoạt Đảng</div>
      </div>
    </div>
    <div>
      {% if user %}
        <div style="text-align:right">
          <div style="font-weight:600;color:var(--accent)">{{ user.full_name }}</div>
          <div class="small muted">{{ user.role|upper }}</div>
          <div style="margin-top:6px"><a class="btn btn-light" href="{{ url_for('logout') }}">Đăng xuất</a></div>
        </div>
      {% else %}
        <a class="btn btn-light" href="{{ url_for('login') }}">Đăng nhập</a>
      {% endif %}
    </div>
  </header>

  {% if user %}
  <div class="navbar">
    <div class="container" style="display:flex;justify-content:space-between;align-items:center">
      <div>
        <a href="{{ url_for('admin_index') }}" class="small" style="color:#fff;margin-right:12px">Dashboard</a>
        <a href="{{ url_for('chi_bo_list') }}" class="small" style="color:#fff;margin-right:12px">Chi bộ</a>
        <a href="{{ url_for('dang_vien_list') }}" class="small" style="color:#fff;margin-right:12px">Đảng viên</a>
        <a href="{{ url_for('rag_chat') }}" class="small" style="color:#fff;margin-right:12px">Chatbot AI</a>
        <a href="{{ url_for('upload_page') }}" class="small" style="color:#fff">Upload</a>
      </div>
      <div>
        {% if user.role == 'admin' %}
          <a href="{{ url_for('admin_user_list') }}" class="small" style="color:#fff">Quản lý người dùng</a>
        {% endif %}
      </div>
    </div>
  </div>
  {% endif %}

  <div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, msg in messages %}
          <div class="card">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {% block content %}{% endblock %}
  </div>
</body>
</html>
"""

# rag_chat template (embedded). Uses simple JS to call /api/chat
RAG_CHAT_HTML = """
{% extends 'base' %}
{% block title %}Chatbot AI - RAG{% endblock %}
{% block extra_head %}
<script>
function addMsg(text, who='bot', meta='') {
    const box = document.getElementById('chat_window');
    const div = document.createElement('div');
    div.className = 'msg ' + (who==='me' ? 'me' : 'bot');
    div.innerHTML = text + (meta ? '<div class="small muted" style="margin-top:6px">'+meta+'</div>':'');
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}
async function sendQuestion() {
    const q = document.getElementById('question').value.trim();
    if(!q) return;
    addMsg(q,'me');
    document.getElementById('question').value='';
    addMsg('Đang suy nghĩ...','bot');
    try {
        const fd = new FormData();
        fd.append('question', q);
        const res = await fetch('{{ url_for("rag_chat") }}', {method:'POST', body:fd});
        const text = await res.text();
        // server returns full page HTML after POST; but we also support JSON via /api/chat
        // prefer API:
        const api = await fetch('{{ url_for("api_chat") }}', {
            method:'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({question: q})
        });
        const data = await api.json();
        // remove last "Đang suy nghĩ..."
        const box = document.getElementById('chat_window');
        if (box.lastChild && box.lastChild.textContent.includes('Đang suy nghĩ')) box.removeChild(box.lastChild);
        addMsg(data.answer || data.error || 'Không có phản hồi.', 'bot', data.source || '');
    } catch(err){
        console.error(err);
        addMsg('Lỗi kết nối.', 'bot');
    }
}
async function uploadFile() {
    const f = document.getElementById('file').files[0];
    if(!f){ alert('Chọn file!'); return; }
    const fd = new FormData();
    fd.append('file', f);
    const res = await fetch('{{ url_for("upload_file") }}', {method:'POST', body:fd});
    const data = await res.json();
    if(data.error){ alert(data.error); return; }
    document.getElementById('file').value='';
    alert('Upload thành công: ' + data.filename);
    // refresh doc list
    loadDocs();
}
async function loadDocs(){
    const res = await fetch('{{ url_for("list_docs") }}');
    const data = await res.json();
    const box = document.getElementById('doc_list');
    box.innerHTML='';
    if(data.length===0){ box.innerHTML='<div class="small muted">Chưa có tài liệu.</div>'; return; }
    data.forEach(d=>{
        const el = document.createElement('div');
        el.className='doc-card';
        el.style.marginBottom='8px';
        el.innerHTML = '<strong>'+d.filename+'</strong><div class="small muted">Uploaded: '+d.created_at+'</div>';
        box.appendChild(el);
    });
}
document.addEventListener('DOMContentLoaded', function(){
    loadDocs();
});
</script>
{% endblock %}
{% block content %}
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div><h3>Chatbot AI — RAG (Tất cả user đều truy cập được)</h3><div class="small muted">Upload tài liệu, sau đó hỏi để bot trả lời dựa trên tài liệu.</div></div>
    <div class="small muted">Embedding: {{ 'ENABLED' if embed_enabled else 'DISABLED (fallback random)' }}</div>
  </div>
  <hr>
  <div style="display:grid;grid-template-columns:1fr 320px;gap:12px">
    <div>
      <div id="chat_window" class="chat-window card" aria-live="polite">
        <div class="small muted">Chat bắt đầu — hỏi điều gì liên quan đến tài liệu đã upload.</div>
      </div>

      <div style="display:flex;gap:8px;margin-top:8px">
        <input id="question" type="text" placeholder="Hỏi về tài liệu..." />
        <button class="btn btn-primary" onclick="sendQuestion()">Gửi</button>
      </div>

      <div style="margin-top:10px">
        <h5 class="small muted">Nguồn trả lời (nếu có):</h5>
        <div id="used_docs" class="small muted">Bot sẽ hiển thị các tài liệu được dùng để trả lời.</div>
      </div>
    </div>

    <div>
      <div class="card">
        <h5>Tải tài liệu</h5>
        <div class="small muted">Chấp nhận: .pdf, .txt, .md</div>
        <div style="margin-top:8px;display:flex;gap:8px">
          <input id="file" type="file" />
          <button class="btn btn-success" onclick="uploadFile()">Upload</button>
        </div>
      </div>

      <div class="card" style="margin-top:12px">
        <h5>Danh sách tài liệu</h5>
        <div id="doc_list" style="margin-top:8px"></div>
      </div>
    </div>
  </div>
</div>
{% endblock %}
"""

# other templates: login, admin dashboard, user management, chi_bo, dang_vien, sinh_hoat
LOGIN_HTML = """
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Login</title>
<style>
 body{font-family:Arial;background:#f4f6f8;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
 .card{background:#fff;padding:20px;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,0.06);width:360px}
 input{width:100%;padding:8px;margin:8px 0;border:1px solid #dfe6ea;border-radius:6px}
 .btn{padding:8px 12px;border-radius:6px;border:0;background:#0B6E3B;color:#fff;cursor:pointer}
</style></head>
<body>
  <div class="card">
    <h3>Đăng nhập</h3>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for c,m in messages %}<div style="color:red">{{ m }}</div>{% endfor %}
      {% endif %}
    {% endwith %}
    <form method="post" action="{{ url_for('login') }}">
      <input name="username" placeholder="Tên đăng nhập" required>
      <input name="password" placeholder="Mật khẩu" type="password" required>
      <div style="display:flex;gap:8px;justify-content:space-between;align-items:center">
        <button class="btn" type="submit">Đăng nhập</button>
        <a href="#" onclick="alert('Demo users: admin/Test@321, user_demo/Test@123')">?</a>
      </div>
    </form>
  </div>
</body>
</html>
"""

ADMIN_DASH_HTML = """
{% extends 'base' %}
{% block title %}Admin Dashboard{% endblock %}
{% block content %}
<div class="card">
  <h3>Xin chào {{ user.full_name }}</h3>
  <p class="small muted">Số chi bộ: {{ chibos|length }} — Số đảng viên: {{ dv_count }} — Số buổi: {{ sh_count }}</p>
  <div style="margin-top:12px">
    <a class="btn btn-primary" href="{{ url_for('chi_bo_list') }}">Quản lý Chi bộ</a>
    <a class="btn btn-primary" href="{{ url_for('dang_vien_list') }}">Quản lý Đảng viên</a>
    <a class="btn btn-primary" href="{{ url_for('rag_chat') }}">Chatbot AI</a>
    <a class="btn btn-success" href="{{ url_for('upload_page') }}">Upload</a>
  </div>
</div>
{% endblock %}
"""

ADMIN_USERS_HTML = """
{% extends 'base' %}
{% block title %}Quản lý người dùng{% endblock %}
{% block content %}
<div class="card">
  <h4>Quản lý người dùng</h4>
  {% if success %}<div class="small muted" style="color:green">{{ success }}</div>{% endif %}
  {% if error %}<div class="small muted" style="color:red">{{ error }}</div>{% endif %}
  <form method="post" action="{{ url_for('admin_user_add') }}" style="display:flex;gap:8px;margin-top:8px">
    <input name="username" placeholder="username" required>
    <input name="full_name" placeholder="Họ và tên" required>
    <input name="password" placeholder="Mật khẩu" required>
    <select name="role"><option value="user">User</option><option value="admin">Admin</option></select>
    <button class="btn btn-success" type="submit">Thêm</button>
  </form>
  <hr>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr><th>Username</th><th>Họ tên</th><th>Role</th><th>Hành động</th></tr></thead>
    <tbody>
      {% for u in users %}
      <tr>
        <td><strong>{{ users[u].username }}</strong></td>
        <td>{{ users[u].full_name }}</td>
        <td>{{ users[u].role }}</td>
        <td>
          {% if users[u].username != 'admin' %}
          <form method="post" action="{{ url_for('admin_user_reset', username=users[u].username) }}" style="display:inline">
            <button class="btn btn-light" type="submit">Reset MK</button>
          </form>
          <form method="post" action="{{ url_for('admin_user_delete', username=users[u].username) }}" style="display:inline">
            <button class="btn btn-light" type="submit" onclick="return confirm('Xóa?')">Xóa</button>
          </form>
          {% else %}System{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
"""

CHI_BO_HTML = """
{% extends 'base' %}
{% block title %}Danh sách Chi bộ{% endblock %}
{% block content %}
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <h4>Danh sách Chi bộ</h4>
    {% if user.role == 'admin' %}
    <form method="post" action="{{ url_for('chi_bo_create') }}" style="display:flex;gap:8px">
      <input name="name" placeholder="Tên chi bộ" required>
      <button class="btn btn-success" type="submit">Tạo</button>
    </form>
    {% endif %}
  </div>
  <div style="margin-top:12px">
    {% for c in chibos %}
      <div class="card" style="margin-bottom:8px;display:flex;justify-content:space-between">
        <div>
          <strong>{{ c.name }}</strong>
          <div class="small muted">{{ c.description or '' }}</div>
        </div>
        <div>
          <a class="btn btn-light" href="{{ url_for('chi_bo_members', chi_bo_id=c.id) }}">Thành viên</a>
          <a class="btn btn-light" href="{{ url_for('chi_bo_sinh_hoat', chi_bo_id=c.id) }}">Buổi</a>
          {% if user.role == 'admin' %}
          <form method="post" action="{{ url_for('chi_bo_delete', chi_bo_id=c.id) }}" style="display:inline">
            <button class="btn btn-light" type="submit" onclick="return confirm('Xóa chi bộ?')">Xóa</button>
          </form>
          {% endif %}
        </div>
      </div>
    {% else %}
      <div class="small muted">Chưa có chi bộ.</div>
    {% endfor %}
  </div>
</div>
{% endblock %}
"""

DANG_VIEN_HTML = """
{% extends 'base' %}
{% block title %}Đảng viên{% endblock %}
{% block content %}
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center"><h4>Đảng viên</h4>
  {% if user.role == 'admin' %}
    <form method="post" action="{{ url_for('dang_vien_create') }}" style="display:flex;gap:8px">
      <input name="full_name" placeholder="Họ và tên" required>
      <input name="email" placeholder="Email">
      <select name="chi_bo_id">
        <option value="">— Chọn chi bộ —</option>
        {% for c in chibos %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}
      </select>
      <button class="btn btn-success" type="submit">Thêm</button>
    </form>
  {% endif %}
  </div>
  <div style="margin-top:12px">
    <table style="width:100%">
      <thead><tr><th>#</th><th>Họ tên</th><th>Email</th><th>Chi bộ</th><th>Hành động</th></tr></thead>
      <tbody>
      {% for m in members %}
        <tr>
          <td>{{ loop.index }}</td>
          <td>{{ m.full_name }}</td>
          <td>{{ m.email or '-' }}</td>
          <td>{{ m.chi_bo.name if m.chi_bo else '-' }}</td>
          <td>
            <a class="btn btn-light" href="{{ url_for('dang_vien_detail', dv_id=m.id) }}">Chi tiết</a>
            {% if user.role == 'admin' %}
            <form method="post" action="{{ url_for('dang_vien_delete', dv_id=m.id) }}" style="display:inline">
              <button class="btn btn-light" type="submit">Xóa</button>
            </form>
            {% endif %}
          </td>
        </tr>
      {% else %}
        <tr><td colspan="5" class="small muted">Chưa có đảng viên.</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
"""

DANG_VIEN_DETAIL_HTML = """
{% extends 'base' %}
{% block title %}Hồ sơ{% endblock %}
{% block content %}
<div class="card">
  <h4>{{ dv.full_name }}</h4>
  <div class="small muted">Username: {{ dv.username or '-' }} — Email: {{ dv.email or '-' }}</div>
  <div style="margin-top:12px">
    <h5>Lịch sử sinh hoạt</h5>
    <table style="width:100%">
      <thead><tr><th>Buổi</th><th>Ngày</th><th>Trạng thái</th><th>Lý do vắng</th></tr></thead>
      <tbody>
        {% for a in attendances %}
          <tr>
            <td>{{ a.sinh_hoat.tieu_de }}</td>
            <td>{{ a.sinh_hoat.ngay_sinh_hoat.strftime('%Y-%m-%d') }}</td>
            <td>{{ 'Có mặt' if a.co_mat else 'Vắng' }}</td>
            <td>{{ a.ly_do_vang or '-' }}</td>
          </tr>
        {% else %}
          <tr><td colspan="4" class="small muted">Không có dữ liệu.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
"""

UPLOAD_HTML = """
{% extends 'base' %}
{% block title %}Upload tài liệu{% endblock %}
{% block content %}
<div class="card">
  <h4>Upload tài liệu cho Chatbot</h4>
  <div class="small muted">Hỗ trợ: .pdf, .txt, .md</div>
  <form method="post" action="{{ url_for('upload_file') }}" enctype="multipart/form-data" style="margin-top:8px">
    <input type="file" name="file" required>
    <div style="margin-top:8px"><button class="btn btn-success" type="submit">Upload & Nhúng</button></div>
  </form>
</div>
{% endblock %}
"""

# Register template loader mapping for render_template_string
TEMPLATES = {
    "base": BASE_HTML,
    "rag_chat.html": RAG_CHAT_HTML,
    "login.html": LOGIN_HTML,
    "admin_dashboard.html": ADMIN_DASH_HTML,
    "admin_users.html": ADMIN_USERS_HTML,
    "chi_bo_list.html": CHI_BO_HTML,
    "dang_vien_list.html": DANG_VIEN_HTML,
    "dang_vien_detail.html": DANG_VIEN_DETAIL_HTML,
    "upload.html": UPLOAD_HTML,
}

def render(name, **kwargs):
    """Render embedded template by name. Allows extending 'base'."""
    # If template extends 'base', Jinja needs base present in globals; we pass map
    env = {}
    env.update(TEMPLATES)
    # Jinja supports providing templates via render_template_string with dict mapping
    tpl = TEMPLATES.get(name)
    if not tpl:
        return "Template not found: " + name
    return render_template_string(tpl, **kwargs, **{"env_templates": env})

# Context processor for user injection
@app.context_processor
def inject_user():
    return {"user": session.get("user")}

# Routes
@app.route("/")
def index():
    # Keep existing login flow: redirect to login if not logged, else admin
    if not session.get("user"):
        return redirect(url_for("login"))
    return redirect(url_for("admin_index"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("admin_index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = USERS.get(username)
        if user and user["password"] == password:
            session["user"] = {"username": user["username"], "role": user["role"], "full_name": user["full_name"]}
            flash("Đăng nhập thành công.", "success")
            return redirect(url_for("admin_index"))
        flash("Sai tên đăng nhập hoặc mật khẩu.", "danger")
    return render("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/admin")
def admin_index():
    if not session.get("user"):
        return redirect(url_for("login"))
    db = SessionLocal()
    chibos = db.query(ChiBo).order_by(ChiBo.name).all()
    dv_count = db.query(DangVien).count()
    sh_count = db.query(SinhHoatDang).count()
    db.close()
    return render("admin_dashboard.html", chibos=chibos, dv_count=dv_count, sh_count=sh_count)

# === User management (admin) ===
@app.route("/admin/users")
def admin_user_list():
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    return render("admin_users.html", users=USERS, success=request.args.get("success"), error=request.args.get("error"))

@app.route("/admin/users/add", methods=["POST"])
def admin_user_add():
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "user")
    if not username or not full_name or not password:
        return redirect(url_for("admin_user_list", error="Thiếu thông tin"))
    if username in USERS:
        return redirect(url_for("admin_user_list", error="Username đã tồn tại"))
    USERS[username] = {"username": username, "password": password, "role": role, "full_name": full_name}
    return redirect(url_for("admin_user_list", success="Thêm user thành công"))

@app.route("/admin/users/reset/<username>", methods=["POST"])
def admin_user_reset(username):
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    u = USERS.get(username)
    if not u:
        return redirect(url_for("admin_user_list", error="Không tìm thấy user"))
    u["password"] = "Test@123"
    return redirect(url_for("admin_user_list", success=f"Reset mật khẩu {username} -> Test@123"))

@app.route("/admin/users/delete/<username>", methods=["POST"])
def admin_user_delete(username):
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    if username == "admin":
        return redirect(url_for("admin_user_list", error="Không thể xóa admin"))
    if username in USERS:
        USERS.pop(username)
        return redirect(url_for("admin_user_list", success="Xóa thành công"))
    return redirect(url_for("admin_user_list", error="Không tìm thấy user"))

# === Chi bộ routes ===
@app.route("/chi_bo", methods=["GET"])
def chi_bo_list():
    if not session.get("user"):
        return redirect(url_for("login"))
    db = SessionLocal()
    chibos = db.query(ChiBo).order_by(ChiBo.name).all()
    db.close()
    return render("chi_bo_list.html", chibos=chibos)

@app.route("/chi_bo/create", methods=["POST"])
def chi_bo_create():
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip() if request.form.get("description") else None
    if not name:
        flash("Tên chi bộ required", "danger")
        return redirect(url_for("chi_bo_list"))
    db = SessionLocal()
    exists = db.query(ChiBo).filter(ChiBo.name==name).first()
    if exists:
        flash("Chi bộ đã tồn tại", "danger")
        db.close()
        return redirect(url_for("chi_bo_list"))
    cb = ChiBo(name=name, description=desc)
    db.add(cb); db.commit(); db.close()
    flash("Tạo chi bộ thành công", "success")
    return redirect(url_for("chi_bo_list"))

@app.route("/chi_bo/<int:chi_bo_id>/delete", methods=["POST"])
def chi_bo_delete(chi_bo_id):
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    db = SessionLocal()
    cb = db.query(ChiBo).get(chi_bo_id)
    if cb:
        db.delete(cb); db.commit()
        flash("Xoá chi bộ", "success")
    db.close()
    return redirect(url_for("chi_bo_list"))

@app.route("/chi_bo/<int:chi_bo_id>/members")
def chi_bo_members(chi_bo_id):
    if not session.get("user"):
        return redirect(url_for("login"))
    db = SessionLocal()
    cb = db.query(ChiBo).get(chi_bo_id)
    members = db.query(DangVien).filter(DangVien.chi_bo_id==chi_bo_id).all()
    chibos = db.query(ChiBo).all()
    db.close()
    return render_template_string(TEMPLATES["dang_vien.html"], chi=cb, members=members, chibos=chibos, user=session.get("user"))

# === Dang vien routes ===
@app.route("/dang_vien", methods=["GET"])
def dang_vien_list():
    if not session.get("user"):
        return redirect(url_for("login"))
    db = SessionLocal()
    members = db.query(DangVien).order_by(DangVien.full_name).all()
    chibos = db.query(ChiBo).all()
    db.close()
    return render("dang_vien_list.html", members=members, chibos=chibos)

@app.route("/dang_vien/create", methods=["POST"])
def dang_vien_create():
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip() or None
    chi_bo_id = request.form.get("chi_bo_id") or None
    db = SessionLocal()
    dv = DangVien(full_name=full_name, email=email, chi_bo_id=chi_bo_id)
    db.add(dv); db.commit(); db.close()
    flash("Thêm đảng viên thành công", "success")
    return redirect(url_for("dang_vien_list"))

@app.route("/dang_vien/<int:dv_id>")
def dang_vien_detail(dv_id):
    if not session.get("user"):
        return redirect(url_for("login"))
    db = SessionLocal()
    dv = db.query(DangVien).get(dv_id)
    attendances = db.query(SinhHoatAttendance).filter(SinhHoatAttendance.dang_vien_id==dv_id).all()
    db.close()
    return render("dang_vien_detail.html", dv=dv, attendances=attendances)

@app.route("/dang_vien/<int:dv_id>/delete", methods=["POST"])
def dang_vien_delete(dv_id):
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    db = SessionLocal()
    dv = db.query(DangVien).get(dv_id)
    if dv:
        db.delete(dv); db.commit()
        flash("Xóa đảng viên", "success")
    db.close()
    return redirect(url_for("dang_vien_list"))

# === Sinh hoạt routes (basic) ===
@app.route("/chi_bo/<int:chi_bo_id>/sinh_hoat")
def chi_bo_sinh_hoat(chi_bo_id):
    if not session.get("user"):
        return redirect(url_for("login"))
    db = SessionLocal()
    chi = db.query(ChiBo).get(chi_bo_id)
    sinhhoats = db.query(SinhHoatDang).filter(SinhHoatDang.chi_bo_id==chi_bo_id).order_by(SinhHoatDang.ngay_sinh_hoat.desc()).all()
    dangviens = db.query(DangVien).filter(DangVien.chi_bo_id==chi_bo_id).all()
    db.close()
    return render("chi_bo_list.html", chibos=[chi])  # simplified: redirect to chi_bo_list view

@app.route("/chi_bo/<int:chi_bo_id>/sinh_hoat/create", methods=["POST"])
def chi_bo_sinh_hoat_create(chi_bo_id):
    if not session.get("user") or session["user"]["role"] not in ("admin",):
        return redirect(url_for("login"))
    tieu_de = request.form.get("tieu_de") or "Buổi sinh hoạt"
    ngay = request.form.get("ngay_sinh_hoat")
    hinh_thuc = request.form.get("hinh_thuc") or "truc_tiep"
    noi_dung = request.form.get("noi_dung") or None
    try:
        ngay_dt = datetime.fromisoformat(ngay)
    except Exception:
        ngay_dt = datetime.utcnow()
    db = SessionLocal()
    sh = SinhHoatDang(chi_bo_id=chi_bo_id, tieu_de=tieu_de, ngay_sinh_hoat=ngay_dt, hinh_thuc=hinh_thuc, noi_dung=noi_dung)
    db.add(sh); db.commit(); db.close()
    flash("Tạo buổi thành công", "success")
    return redirect(url_for("chi_bo_sinh_hoat", chi_bo_id=chi_bo_id))

# === Upload & RAG ===
@app.route("/upload", methods=["GET"])
def upload_page():
    if not session.get("user"):
        return redirect(url_for("login"))
    return render("upload.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    if not session.get("user"):
        return jsonify({"error": "Unauthorized"}), 403
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file"}), 400
    filename = secure_filename(f.filename)
    if not allowed_file(filename):
        return jsonify({"error": "File type not allowed"}), 400
    ext = filename.rsplit(".",1)[1].lower()
    raw = None
    if ext == "pdf":
        raw = extract_text_from_pdf(f.stream)
    else:
        try:
            raw = f.stream.read().decode("utf-8", errors="ignore")
        except Exception:
            raw = ""
    if not raw:
        raw = ""
    # create embedding (may be fallback)
    vec = embed_text(raw)
    vec_bytes = numpy_to_bytes(vec)
    # save file to uploads folder for reference
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    f.stream.seek(0)
    f.save(path)
    # persist to DB
    db = SessionLocal()
    doc = RAGDocument(filename=filename, text=raw, embedding=vec_bytes)
    db.add(doc); db.commit(); db.close()
    return jsonify({"filename": filename, "summary": (raw[:800] + '...') if raw else ''})

@app.route("/docs/list")
def list_docs():
    if not session.get("user"):
        return jsonify([]), 403
    db = SessionLocal()
    docs = db.query(RAGDocument).order_by(RAGDocument.created_at.desc()).all()
    out = []
    for d in docs:
        out.append({"id": d.id, "filename": d.filename, "created_at": d.created_at.strftime("%Y-%m-%d %H:%M")})
    db.close()
    return jsonify(out)

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

# RAG Chat page (GET renders, POST handled by API below)
@app.route("/rag_chat", methods=["GET", "POST"])
def rag_chat():
    if not session.get("user"):
        return redirect(url_for("login"))
    # Keep POST to support html form post (but main chat uses /api/chat)
    if request.method == "POST":
        # basic: redirect to GET
        return redirect(url_for("rag_chat"))
    db = SessionLocal()
    docs = db.query(RAGDocument).order_by(RAGDocument.created_at.desc()).all()
    db.close()
    embed_enabled = EMBED_MODEL is not None
    # render with template mapping
    # we use render_template_string and give access to templates via TEMPLATES dict
    return render_template_string(TEMPLATES["rag_chat.html"], embed_enabled=embed_enabled, user=session.get("user"))

# API for chat (returns JSON)
@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not session.get("user"):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Empty question"}), 400
    # embed question
    qv = embed_text(question)
    db = SessionLocal()
    docs = db.query(RAGDocument).all()
    sims = []
    for d in docs:
        if d.embedding:
            try:
                dv = bytes_to_numpy(d.embedding)
                sim = cosine_sim(qv, dv)
                sims.append((sim, d))
            except Exception as e:
                continue
    sims.sort(key=lambda x: x[0], reverse=True)
    # take top 3 with sim > threshold if any
    top = [doc for sim, doc in sims[:3] if sim > 0.0]
    context = "\n\n".join([t.text for t in top]) if top else ""
    prompt = f"Dựa vào ngữ cảnh sau, trả lời ngắn gọn bằng tiếng Việt:\n\nNgữ cảnh:\n{context}\n\nCâu hỏi: {question}"
    answer = llm_answer(prompt)
    # prepare source info
    source_files = [t.filename for t in top]
    db.close()
    return jsonify({"answer": answer, "source": ", ".join(source_files)})

# For web chat fallback (non-AJAX) - return basic text (not used by default)
@app.route("/chat", methods=["POST"])
def chat_post():
    if not session.get("user"):
        return redirect(url_for("login"))
    q = request.form.get("prompt") or request.form.get("message") or ""
    if not q:
        flash("Chưa nhập câu hỏi", "danger")
        return redirect(url_for("rag_chat"))
    # use same API
    resp = api_chat()
    return resp

# small API to fetch history for user profile (demo)
@app.route("/api/dang_vien_history_by_username")
def api_dv_history():
    username = request.args.get("username")
    if not username:
        return jsonify([])
    db = SessionLocal()
    dv = db.query(DangVien).filter(DangVien.username==username).first()
    if not dv:
        return jsonify([])
    data = []
    for a in dv.attendances:
        data.append({
            "tieu_de": a.sinh_hoat.tieu_de,
            "ngay": a.sinh_hoat.ngay_sinh_hoat.strftime("%Y-%m-%d"),
            "co_mat": bool(a.co_mat),
            "ly_do_vang": a.ly_do_vang
        })
    db.close()
    return jsonify(data)

# Simple route to admin user list using embedded template
@app.route("/admin/users_view")
def admin_users_view():
    if not session.get("user") or session["user"]["role"] != "admin":
        return redirect(url_for("login"))
    return render_template_string(TEMPLATES["admin_users.html"], users=USERS, user=session.get("user"))

# Expose other embedded templates via helper render() if needed
@app.route("/upload_page")
def upload_page_redirect():
    return redirect(url_for("upload_page"))

# error handlers
@app.errorhandler(500)
def internal_err(e):
    return f"Internal Server Error: {e}", 500

# Start app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # set debug False on render; ok True locally
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
