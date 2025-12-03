import os
import json
import numpy as np
from flask import Flask, render_template, request, redirect, session, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# OPTIONAL: If you use sentence-transformers:
try:
    from sentence_transformers import SentenceTransformer
    EMBED_AVAILABLE = True
except Exception:
    EMBED_AVAILABLE = False

# OPTIONAL: If you use PyPDF2 to read PDF:
try:
    import PyPDF2
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

# OPTIONAL: OpenAI for LLM fallback
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# ========== Configuration ==========
UPLOAD_FOLDER = "uploads"
ALLOWED_EXT = {"txt", "pdf", "md"}

SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-key")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = SECRET_KEY

if OPENAI_AVAILABLE and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# ========== Simple demo user store ==========
# In production use database + hashed passwords.
USERS = {
    "admin": {
        "username": "admin",
        "password": "Test@321",
        "role": "admin",
        "full_name": "Administrator"
    },
    "user_demo": {
        "username": "user_demo",
        "password": "Test@123",
        "role": "user",
        "full_name": "Người dùng Demo"
    }
}

# ========== In-memory RAG store ==========
DOCUMENTS = []   # list of dicts: {"text": "...", "meta": {...}}
EMBEDDINGS = [] # list of numpy arrays

# Load embedding model if available
EMBED_MODEL = None
if EMBED_AVAILABLE:
    # Choose model you installed. Replace with a Vietnamese SBERT if desired.
    try:
        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        EMBED_MODEL = None

# ========== Helpers ==========
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def embed_text(text):
    """
    Return vector embedding for text.
    Uses sentence-transformers if available; otherwise returns random vector (placeholder).
    """
    if EMBED_MODEL:
        emb = EMBED_MODEL.encode(text, convert_to_numpy=True)
        return emb
    else:
        # placeholder deterministic pseudo-embedding (not for production)
        rng = np.random.RandomState(abs(hash(text)) % (2**32))
        return rng.normal(size=(384,))

def cosine_sim(a, b):
    if a is None or b is None:
        return -1.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return -1.0
    return float(np.dot(a, b) / (na * nb))

def extract_text_from_pdf(stream):
    if not PDF_AVAILABLE:
        return ""
    try:
        reader = PyPDF2.PdfReader(stream)
        texts = []
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                texts.append(txt)
        return "\n".join(texts)
    except Exception:
        return ""

def llm_answer(prompt, max_tokens=300):
    """
    Fallback LLM answer using OpenAI. If OpenAI not configured, returns a placeholder.
    """
    if OPENAI_AVAILABLE and OPENAI_API_KEY:
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role":"system","content":"Bạn là trợ lý hữu ích."},
                          {"role":"user","content":prompt}],
                max_tokens=max_tokens,
                temperature=0.2
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[LLM error] {str(e)}"
    else:
        # fallback placeholder so chatbot never stays silent
        return "Xin lỗi, hiện tại bot chưa kết nối tới LLM. (Bạn có thể cài đặt OPENAI_API_KEY)."

# ========== Routes ==========
@app.route("/")
def index():
    user = session.get("user")
    return render_template("index.html", user=user)

# -------- Login/Logout ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in redirect
    if session.get("user"):
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = USERS.get(username)

        if not user:
            # If username not found, for security we show same behavior as wrong password
            # But requirement: only user_demo must show explicit error.
            if username == "user_demo":
                flash("Tài khoản không tồn tại.", "danger")
            # For admin or other usernames do not flash admin-specific info
            return render_template("login.html", show_demo=True)

        # Found user
        if password != user["password"]:
            # Requirement: *If admin* enters wrong password -> do NOT show flash error
            if username == "admin":
                # silent fail: re-render login without flashing
                return render_template("login.html", show_demo=True)
            else:
                # For other users (including user_demo) show error
                flash("Sai tên đăng nhập hoặc mật khẩu.", "danger")
                return render_template("login.html", show_demo=True)

        # Success login
        session["user"] = {
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"]
        }
        return redirect("/")

    # GET
    return render_template("login.html", show_demo=True)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# -------- Upload documents to RAG ----------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    user = session.get("user")
    if not user:
        return redirect("/login")

    if request.method == "POST":
        if "file" not in request.files:
            flash("Không có tệp được gửi.", "danger")
            return redirect("/upload")
        f = request.files["file"]
        if f.filename == "":
            flash("Không có tệp được chọn.", "danger")
            return redirect("/upload")
        if not allowed_file(f.filename):
            flash("Định dạng tệp không được hỗ trợ.", "danger")
            return redirect("/upload")

        filename = secure_filename(f.filename)
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        f.seek(0)
        f.save(path)

        # Read content
        ext = filename.rsplit(".", 1)[1].lower()
        text = ""
        if ext == "txt" or ext == "md":
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        elif ext == "pdf":
            with open(path, "rb") as fh:
                text = extract_text_from_pdf(fh) or ""

        if not text:
            flash("Không thể đọc nội dung tệp hoặc tệp rỗng.", "danger")
            return redirect("/upload")

        # Optionally split long text into chunks (simple split by paragraphs)
        chunks = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not chunks:
            chunks = [text[:2000]]

        added = 0
        for ch in chunks:
            emb = embed_text(ch)
            DOCUMENTS.append({"text": ch, "meta": {"filename": filename}})
            EMBEDDINGS.append(emb)
            added += 1

        flash(f"Tải lên thành công: {added} chunk(s) đã được nhúng.", "success")
        return redirect("/upload")

    return render_template("upload.html", user=user)

# -------- Chat endpoint ----------
@app.route("/chat", methods=["POST"])
def chat():
    user = session.get("user")
    # If you want anonymous chat allow even without login. Here require login.
    if not user:
        return jsonify({"reply": "Bạn cần đăng nhập để sử dụng chatbot."})

    data = request.get_json() or {}
    question = data.get("message", "").strip()
    if not question:
        return jsonify({"reply": "Vui lòng nhập câu hỏi."})

    # If no documents uploaded: fallback to LLM
    if len(DOCUMENTS) == 0 or len(EMBEDDINGS) == 0:
        fallback = llm_answer(question)
        return jsonify({"reply": fallback})

    # compute embedding of question
    q_emb = embed_text(question)

    # compute similarities
    sims = [cosine_sim(q_emb, e) for e in EMBEDDINGS]
    # find top-k
    k = 3
    idxs = np.argsort(sims)[-k:][::-1].tolist()
    top_sims = [(i, sims[i]) for i in idxs]

    # pick best context if above threshold
    best_idx, best_score = top_sims[0]
    THRESH = 0.45  # tune this threshold
    if best_score >= THRESH:
        # gather top contexts
        contexts = []
        for i, s in top_sims:
            contexts.append(f"(score={s:.3f}) {DOCUMENTS[i]['text'][:1500]}")  # truncate for prompt
        context_text = "\n\n---\n\n".join(contexts)

        prompt = f"""
Bạn là trợ lý (chatbot) trả lời bằng tiếng Việt.
Sử dụng NGAY và CHỈ những thông tin liên quan trong phần "Tài liệu" nếu có thể.
Nếu Tài liệu không đủ thì có thể bổ sung bằng kiến thức ngoài tài liệu.
Trả lời thật ngắn gọn, dễ hiểu, và trích dẫn (tên file trong uploads) nếu liên quan.

Tài liệu:
{context_text}

Câu hỏi:
{question}

Yêu cầu: nếu dùng tài liệu hãy bắt đầu câu trả lời bằng "[Tài liệu]" - nếu không, bắt đầu bằng "[Ngoài tài liệu]".
"""
        answer = llm_answer(prompt)
        return jsonify({"reply": answer})
    else:
        # fallback to LLM
        fallback = llm_answer(question)
        return jsonify({"reply": fallback})

# -------- Simple page to view chat UI ----------
@app.route("/chat-ui")
def chat_ui():
    user = session.get("user")
    if not user:
        return redirect("/login")
    return render_template("chat.html", user=user)

# Serve uploads (optional)
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== Run ==========
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
