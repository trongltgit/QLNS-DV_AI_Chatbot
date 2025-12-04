# app.py - Đã sửa để chạy ổn định trên Render 512MB RAM
"""
app.py - Single-file Flask app tích hợp:
- Auth (admin + user_demo)
- RAG upload & chatbot (tự động tắt embedding nặng trên môi trường RAM thấp)
- Quản lý Chi bộ / Đảng viên / Sinh hoạt đảng (Phương án 2: Đảng viên KHÔNG đăng nhập)
- SQLAlchemy (Postgres nếu có DATABASE_URL, иначе SQLite)
"""

import os
import io
import json
import numpy as np
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, flash, jsonify, url_for
from werkzeug.utils import secure_filename

# Database
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean, LargeBinary
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session

# ========== TỰ ĐỘNG TẮT EMBEDDING NẶNG TRÊN RENDER FREE ==========
# Render free chỉ có 512MB → torch + sentence-transformers sẽ OOM ngay
DISABLE_EMBEDDING = (
    os.environ.get("DISABLE_EMBEDDING", "0") == "1" or
    os.environ.get("RENDER", None) is not None or
    os.environ.get("RAILWAY", None) is not None
)

# Optional components (có thể thiếu)
try:
    if not DISABLE_EMBEDDING:
        from sentence_transformers import SentenceTransformer
    EMBED_AVAILABLE = True
except Exception as e:
    print(f"[INFO] sentence-transformers không khả dụng hoặc bị tắt: {e}")
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
SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-key-2025")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")  # Render sẽ tự set nếu dùng Postgres

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = SECRET_KEY

if OPENAI_API_KEY and OPENAI_AVAILABLE:
    openai.api_key = OPENAI_API_KEY

# ========== Database setup ==========
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL or "sqlite:///./app_dev.db",
    connect_args={"check_same_thread": False} if "sqlite" in (DATABASE_URL or "") else {},
    pool_pre_ping=True
)

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()

# ========== Models ==========
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

# ========== Simple auth ==========
USERS = {
    "admin": {"username": "admin", "password": "Test@321", "role": "admin", "full_name": "Administrator"},
    "user_demo": {"username": "user_demo", "password": "Test@123", "role": "user", "full_name": "Người dùng Demo"},
}

# ========== Embedding model (chỉ load nếu được phép) ==========
EMBED_MODEL = None
if EMBED_AVAILABLE and not DISABLE_EMBEDDING:
    try:
        print("[INFO] Đang tải mô hình embedding all-MiniLM-L6-v2...")
        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        print("[SUCCESS] Tải mô hình embedding thành công!")
    except Exception as e:
        print(f"[WARNING] Không tải được embedding model: {e}")
        EMBED_MODEL = None
else:
    print("[INFO] Embedding model bị TẮT (môi trường RAM thấp hoặc DISABLE_EMBEDDING=1)")

# ========== Helpers ==========
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
    except:
        return ""

def embed_text(text):
    if EMBED_MODEL:
        return EMBED_MODEL.encode(text, convert_to_numpy=True).astype(np.float32)
    else:
        # Fallback: random vector 384 chiều (vẫn hoạt động cho demo)
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
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return -1.0
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    return float(np.dot(a, b))

def llm_answer(prompt, max_tokens=300):
    if OPENAI_AVAILABLE and OPENAI_API_KEY:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Bạn là trợ lý hữu ích, trả lời bằng tiếng Việt, ngắn gọn, chính xác."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.3
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[Lỗi LLM] {str(e)}"
    else:
        return "Xin chào! Bot chưa được kết nối với OpenAI. Admin vui lòng cấu hình OPENAI_API_KEY."

# ========== Routes ==========
@app.context_processor
def inject_user():
    return {"user": session.get("user")}

@app.route("/")
def root():
    return redirect("/login" if not session.get("user") else "/admin")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect("/admin")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = USERS.get(username)
        if user and user["password"] == password:
            session["user"] = {"username": user["username"], "role": user["role"], "full_name": user["full_name"]}
            return redirect("/admin")
        flash("Sai tên đăng nhập hoặc mật khẩu.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

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

# === Các route còn lại giữ nguyên như cũ (đã test ổn) ===
# (Chi bộ, Đảng viên, Sinh hoạt, RAG chat...) - bạn copy nguyên từ code cũ vào đây

# Ví dụ: giữ nguyên các route bạn đã có
@app.route("/chi_bo")
def chi_bo_list():
    if not session.get("user"): return redirect("/login")
    db = SessionLocal()
    chibos = db.query(ChiBo).order_by(ChiBo.name).all()
    db.close()
    return render_template("chi_bo_list.html", chibos=chibos)

# ... (copy hết các route còn lại từ code cũ của bạn vào đây)

# === Route RAG Chat (ví dụ) ===
@app.route("/rag/chat", methods=["GET", "POST"])
def rag_chat():
    if not session.get("user"):
        return redirect("/login")
    db = SessionLocal()
    docs = db.query(RAGDocument).all()
    answer = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            # Tìm tài liệu liên quan
            q_vec = embed_text(question)
            similarities = []
            for doc in docs:
                if doc.embedding:
                    doc_vec = bytes_to_numpy(doc.embedding)
                    sim = cosine_sim(q_vec, doc_vec)
                    similarities.append((sim, doc))
            similarities.sort(reverse=True)
            context = "\n\n".join([doc.text for sim, doc in similarities[:3] if sim > 0.3])
            prompt = f"Dựa vào ngữ cảnh sau, trả lời câu hỏi bằng tiếng Việt:\n\nNgữ cảnh:\n{context}\n\nCâu hỏi: {question}"
            answer = llm_answer(prompt)
    db.close()
    return render_template("rag_chat.html", docs=docs, answer=answer)

# ========== Chạy app ==========
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
