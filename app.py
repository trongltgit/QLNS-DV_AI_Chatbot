"""
app.py - Single-file Flask app integrating:
- Auth (admin + user_demo)
- RAG upload & chatbot
- Chi bộ / Đảng viên / Sinh hoạt management (Phương án 2: Đảng viên KHÔNG đăng nhập)
- SQLAlchemy (Postgres if DATABASE_URL provided, else SQLite for local dev)

Before running on Render:
- Add environment variables: DATABASE_URL (optional, recommended), FLASK_SECRET, OPENAI_API_KEY (optional)
- Install dependencies (example):
  pip install flask sqlalchemy psycopg2-binary Jinja2 python-multipart werkzeug sentence-transformers numpy openai PyPDF2 python-docx openpyxl pandas aiofiles
  (remove sentence-transformers if you won't use it)
"""

import os
import io
import json
import base64
import numpy as np
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, flash, jsonify, send_from_directory, url_for
from werkzeug.utils import secure_filename

# Database
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean, LargeBinary
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session

# Optional components
try:
    from sentence_transformers import SentenceTransformer
    EMBED_AVAILABLE = True
except Exception:
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

# ========== Config ==========
UPLOAD_FOLDER = "uploads"
ALLOWED_EXT = {"txt", "pdf", "md"}
SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-key")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)
DATABASE_URL = os.environ.get("DATABASE_URL", None)  # e.g. postgresql://user:pass@host:5432/db

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = SECRET_KEY

if OPENAI_AVAILABLE and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# ========== Database setup ==========
if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    # fallback to SQLite local file for dev
    engine = create_engine("sqlite:///./app_dev.db", connect_args={"check_same_thread": False})

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()


# ========== Models ==========
class ChiBo(Base):
    __tablename__ = "chi_bo"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    dangviens = relationship("DangVien", back_populates="chi_bo")
    sinhhoats = relationship("SinhHoatDang", back_populates="chi_bo")


class DangVien(Base):
    __tablename__ = "dang_vien"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=True)  # optional mã đảng viên
    full_name = Column(String, nullable=False)
    username = Column(String, nullable=True, unique=True)  # optional if you want
    email = Column(String, nullable=True)
    chi_bo_id = Column(Integer, ForeignKey("chi_bo.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    chi_bo = relationship("ChiBo", back_populates="dangviens")
    attendances = relationship("SinhHoatAttendance", back_populates="dang_vien")


class SinhHoatDang(Base):
    __tablename__ = "sinh_hoat_dang"
    id = Column(Integer, primary_key=True, index=True)
    chi_bo_id = Column(Integer, ForeignKey("chi_bo.id"), nullable=False)
    ngay_sinh_hoat = Column(DateTime, nullable=False)
    tieu_de = Column(String, nullable=False)
    noi_dung = Column(Text, nullable=True)
    hinh_thuc = Column(String, default="truc_tiep")
    danh_gia = Column(String, nullable=True)
    ghi_chu = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    chi_bo = relationship("ChiBo", back_populates="sinhhoats")
    attendances = relationship("SinhHoatAttendance", back_populates="sinh_hoat")


class SinhHoatAttendance(Base):
    __tablename__ = "sinh_hoat_attendance"
    id = Column(Integer, primary_key=True, index=True)
    sinh_hoat_id = Column(Integer, ForeignKey("sinh_hoat_dang.id"), nullable=False)
    dang_vien_id = Column(Integer, ForeignKey("dang_vien.id"), nullable=False)
    co_mat = Column(Boolean, default=False)
    ly_do_vang = Column(String, nullable=True)
    ghi_chu = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sinh_hoat = relationship("SinhHoatDang", back_populates="attendances")
    dang_vien = relationship("DangVien", back_populates="attendances")


# For RAG documents store: store text + embedding bytes
class RAGDocument(Base):
    __tablename__ = "rag_documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    embedding = Column(LargeBinary, nullable=True)  # store numpy array bytes
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# ========== Simple auth (demo) ==========
# NOTE: in production use DB users + hashed passwords
USERS = {
    "admin": {"username": "admin", "password": "Test@321", "role": "admin", "full_name": "Administrator"},
    "user_demo": {"username": "user_demo", "password": "Test@123", "role": "user", "full_name": "Người dùng Demo"},
}

# ========== Embedding model (optional) ==========
EMBED_MODEL = None
if EMBED_AVAILABLE:
    try:
        # you can change to a Vietnamese SBERT model if installed
        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        EMBED_MODEL = None


# ========== Helpers ==========
def db_session():
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
        texts = []
        for p in reader.pages:
            t = p.extract_text()
            if t:
                texts.append(t)
        return "\n\n".join(texts)
    except Exception:
        return ""


def embed_text(text):
    """
    Return numpy embedding. If sentence-transformers available, use it.
    Otherwise return deterministic pseudo-random vector for retrieval (still works).
    """
    if EMBED_MODEL:
        v = EMBED_MODEL.encode(text, convert_to_numpy=True)
        return v.astype(np.float32)
    else:
        rng = np.random.RandomState(abs(hash(text)) % (2 ** 32))
        return rng.normal(size=(384,)).astype(np.float32)


def numpy_to_bytes(arr: np.ndarray) -> bytes:
    memfile = io.BytesIO()
    np.save(memfile, arr, allow_pickle=False)
    memfile.seek(0)
    return memfile.read()


def bytes_to_numpy(b: bytes) -> np.ndarray:
    memfile = io.BytesIO(b)
    memfile.seek(0)
    return np.load(memfile, allow_pickle=False)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return -1.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return -1.0
    return float(np.dot(a, b) / (na * nb))


def llm_answer(prompt, max_tokens=300):
    """
    Use OpenAI as fallback. If not configured, return helpful placeholder.
    """
    if OPENAI_AVAILABLE and OPENAI_API_KEY:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Bạn là trợ lý hữu ích, trả lời bằng tiếng Việt."},
                          {"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[LLM error] {str(e)}"
    else:
        # graceful non-empty fallback
        return "Xin lỗi, hiện tại bot chưa kết nối tới LLM. (Admin có thể cài OPENAI_API_KEY)."


# ========== Routes ==========
@app.context_processor
def inject_user():
    return {"user": session.get("user")}


@app.route("/")
def root():
    # if logged in show admin dashboard, else redirect to login
    if session.get("user"):
        return redirect("/admin")
    return redirect("/login")


# ---- AUTH ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect("/admin")
    show_demo = True  # always show demo user_demo credential
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        user = USERS.get(username)
        if not user:
            # only user_demo show explicit error; others silent
            if username == "user_demo":
                flash("Tài khoản không tồn tại.", "danger")
            return render_template("login.html", show_demo=show_demo)
        if password != user["password"]:
            if username == "admin":
                # silent fail for admin
                return render_template("login.html", show_demo=show_demo)
            else:
                flash("Sai tên đăng nhập hoặc mật khẩu.", "danger")
                return render_template("login.html", show_demo=show_demo)
        # success
        session["user"] = {"username": user["username"], "role": user["role"], "full_name": user["full_name"]}
        return redirect("/admin")
    return render_template("login.html", show_demo=show_demo)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")


# ---- Admin dashboard (simple) ----
@app.route("/admin")
def admin_index():
    if not session.get("user"):
        return redirect("/login")
    db = SessionLocal()
    chibos = db.query(ChiBo).order_by(ChiBo.name).all()
    dv_count = db.query(DangVien).count()
    sh_count = db.query(SinhHoatDang).count()
    db.close()
    return render_template("admin_dashboard.html", chibos=chibos, dv_count=dv_count, sh_count=sh_count)


# ---- Chi bộ & Đảng viên management (Phương án 2: Đảng viên do admin quản lý) ----
@app.route("/chi_bo")
def chi_bo_list():
    if not session.get("user"):
        return redirect("/login")
    db = SessionLocal()
    chibos = db.query(ChiBo).order_by(ChiBo.name).all()
    db.close()
    return render_template("chi_bo_list.html", chibos=chibos)


@app.route("/chi_bo/create", methods=["POST"])
def chi_bo_create():
    if not session.get("user"):
        return redirect("/login")
    name = (request.form.get("name") or "").strip()
    desc = request.form.get("description") or ""
    if not name:
        flash("Tên chi bộ là bắt buộc.", "danger")
        return redirect("/chi_bo")
    db = SessionLocal()
    exists = db.query(ChiBo).filter(ChiBo.name == name).first()
    if exists:
        flash("Chi bộ đã tồn tại.", "danger")
        db.close()
        return redirect("/chi_bo")
    cb = ChiBo(name=name, description=desc)
    db.add(cb)
    db.commit()
    db.close()
    flash("Tạo chi bộ thành công.", "success")
    return redirect("/chi_bo")


@app.route("/chi_bo/<int:chi_bo_id>/members")
def chi_bo_members(chi_bo_id):
    if not session.get("user"):
        return redirect("/login")
    db = SessionLocal()
    chi = db.query(ChiBo).filter(ChiBo.id == chi_bo_id).first()
    if not chi:
        db.close()
        return "Chi bộ không tồn tại", 404
    members = db.query(DangVien).filter(DangVien.chi_bo_id == chi_bo_id).order_by(DangVien.full_name).all()
    db.close()
    return render_template("dang_vien_list.html", chi=chi, members=members)


@app.route("/dang_vien/create", methods=["POST"])
def dang_vien_create():
    if not session.get("user"):
        return redirect("/login")
    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    chi_bo_id = request.form.get("chi_bo_id")
    try:
        chi_bo_id = int(chi_bo_id) if chi_bo_id else None
    except:
        chi_bo_id = None
    if not full_name:
        flash("Họ tên là bắt buộc.", "danger")
        return redirect(request.referrer or "/chi_bo")
    db = SessionLocal()
    dv = DangVien(full_name=full_name, email=email, chi_bo_id=chi_bo_id)
    db.add(dv)
    db.commit()
    db.close()
    flash("Thêm đảng viên thành công.", "success")
    return redirect(request.referrer or "/chi_bo")


# ---- Sinh hoạt: list, create, detail, attendance ----
@app.route("/chi_bo/<int:chi_bo_id>/sinh_hoat")
def sinh_hoat_list(chi_bo_id):
    if not session.get("user"):
        return redirect("/login")
    db = SessionLocal()
    chi = db.query(ChiBo).filter(ChiBo.id == chi_bo_id).first()
    if not chi:
        db.close()
        return "Chi bộ không tồn tại", 404
    sinhhoats = db.query(SinhHoatDang).filter(SinhHoatDang.chi_bo_id == chi_bo_id).order_by(SinhHoatDang.ngay_sinh_hoat.desc()).all()
    members = db.query(DangVien).filter(DangVien.chi_bo_id == chi_bo_id).order_by(DangVien.full_name).all()
    db.close()
    return render_template("chi_bo_sinh_hoat.html", chi=chi, sinhhoats=sinhhoats, dangviens=members)


@app.route("/chi_bo/<int:chi_bo_id>/sinh_hoat/create", methods=["POST"])
def sinh_hoat_create(chi_bo_id):
    if not session.get("user"):
        return redirect("/login")
    tieu_de = (request.form.get("tieu_de") or "").strip()
    ngay_str = request.form.get("ngay_sinh_hoat")
    hinh_thuc = request.form.get("hinh_thuc") or "truc_tiep"
    noi_dung = request.form.get("noi_dung") or ""
    ghi_chu = request.form.get("ghi_chu") or ""
    try:
        ngay = datetime.fromisoformat(ngay_str)
    except Exception:
        ngay = datetime.utcnow()
    if not tieu_de:
        flash("Tiêu đề là bắt buộc.", "danger")
        return redirect(f"/chi_bo/{chi_bo_id}/sinh_hoat")
    db = SessionLocal()
    sh = SinhHoatDang(chi_bo_id=chi_bo_id, ngay_sinh_hoat=ngay, tieu_de=tieu_de, noi_dung=noi
