import os
import io
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dang-vien-quan-ly-2026-bi-mat")
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY_DV")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

try:
    import PyPDF2
    import docx
    import pandas as pd
except ImportError:
    pass

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}

USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Nguyễn Văn Bí Thư"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Trần Văn Đảng Viên"},
}

CHI_BO_LIST = {
    "cb01": {"name": "Chi bộ Khối Văn phòng", "users": ["bithu1", "dv01"]},
    "cb02": {"name": "Chi bộ Kỹ thuật", "users": []},
}

NHAN_XET = {}
THONG_BAO = {}

def login_required(role=None):
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if role and session["user"]["role"] != role:
                abort(403)
            return fn(*args, **kwargs)
        return decorated
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def extract_text(filepath):
    ext = filepath.rsplit(".", 1)[1].lower()
    text = ""
    try:
        if ext == "txt":
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif ext == "pdf":
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                text = " ".join([p.extract_text() for p in reader.pages if p.extract_text()])
        elif ext == "docx":
            doc = docx.Document(filepath)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext in ("csv", "xlsx"):
            df = pd.read_csv(filepath) if ext == "csv" else pd.read_excel(filepath)
            text = df.to_string()
    except Exception as e:
        text = f"Lỗi xử lý file: {str(e)}"
    return text

def ai_summarize(text):
    if not client:
        return "Lỗi: Hệ thống chưa nhận được GROQ_API_KEY_DV từ môi trường Render."
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Bạn là chuyên gia tư vấn công tác Đảng. Hãy tóm tắt văn bản chuyên nghiệp, súc tích."},
                {"role": "user", "content": f"Tóm tắt văn bản sau:\n\n{text[:15000]}"}
            ],
            temperature=0.3
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Lỗi AI Groq: {str(e)}"

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        user = USERS.get(u)
        if user and check_password_hash(user["password"], p):
            session["user"] = {"username": u, "role": user["role"], "name": user["name"]}
            flash("Đăng nhập thành công!", "success")
            return redirect(url_for("dashboard"))
        flash("Tên đăng nhập hoặc mật khẩu không đúng.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["user"]["role"]
    if role == "admin": return redirect(url_for("admin_users"))
    if role == "bithu": return redirect(url_for("bithu_home"))
    return redirect(url_for("dangvien_home"))

@app.route("/admin/users")
@login_required("admin")
def admin_users():
    return render_template("admin.html", USERS=USERS, CHI_BO_LIST=CHI_BO_LIST)

@app.route("/admin/add", methods=["POST"])
@login_required("admin")
def admin_add():
    u = request.form.get("username").strip()
    if u in USERS:
        flash("Username đã tồn tại.", "danger")
    else:
        USERS[u] = {
            "password": generate_password_hash(request.form.get("password")),
            "role": request.form.get("role"),
            "name": request.form.get("name")
        }
        cb_id = request.form.get("chi_bo_id")
        if cb_id in CHI_BO_LIST:
            CHI_BO_LIST[cb_id]["users"].append(u)
        flash(f"Đã tạo tài khoản {u}.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/reset/<username>")
@login_required("admin")
def admin_reset_pw(username): # Đã sửa tên hàm khớp với url_for
    if username in USERS:
        USERS[username]["password"] = generate_password_hash("Test@123")
        flash(f"Đã reset mật khẩu {username} về Test@123", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/delete/<username>")
@login_required("admin")
def admin_delete(username):
    if username != "admin":
        USERS.pop(username, None)
        for cb in CHI_BO_LIST.values():
            if username in cb["users"]: cb["users"].remove(username)
        flash(f"Đã xóa {username}.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/move", methods=["POST"])
@login_required("admin")
def admin_move_user(): # Đã sửa tên hàm khớp với url_for
    u = request.form.get("username")
    to_cb = request.form.get("to_cb")
    for cb in CHI_BO_LIST.values():
        if u in cb["users"]: cb["users"].remove(u)
    CHI_BO_LIST[to_cb]["users"].append(u)
    flash(f"Đã chuyển {u}.", "success")
    return redirect(url_for("admin_users"))

@app.route("/bithu", methods=["GET", "POST"])
@login_required("bithu")
def bithu_home():
    u = session["user"]["username"]
    cb_id = next((k for k, v in CHI_BO_LIST.items() if u in v["users"]), None)
    if request.method == "POST":
        target = request.form.get("dv_username")
        note = request.form.get("nhan_xet")
        msg = request.form.get("thong_bao")
        if target and note: NHAN_XET.setdefault(target, []).append({"by": u, "note": note})
        if msg: THONG_BAO.setdefault(cb_id, []).append({"by": u, "note": msg})
        flash("Cập nhật thành công.", "success")
    members = CHI_BO_LIST[cb_id]["users"] if cb_id else []
    return render_template("bithu.html", user=session["user"], members=members, USERS=USERS, cb_id=cb_id, THONG_BAO=THONG_BAO)

@app.route("/dangvien")
@login_required("dangvien")
def dangvien_home():
    u = session["user"]["username"]
    cb_id = next((k for k, v in CHI_BO_LIST.items() if u in v["users"]), None)
    return render_template("dangvien.html", user=session["user"], reviews=NHAN_XET.get(u, []), notices=THONG_BAO.get(cb_id, []) if cb_id else [])

@app.route("/upload", methods=["POST"])
@login_required()
def upload_file(): # Hàm xử lý AI
    file = request.files.get("file")
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)
        summary_result = ai_summarize(extract_text(path))
        return render_template("ai_result.html", summary=summary_result)
    flash("File không hợp lệ.", "danger")
    return redirect(url_for("dashboard"))

@app.route("/download/<type>")
@login_required()
def download_template(type):
    output = io.BytesIO()
    content = f"MAU VAN BAN: {type.upper()}\nDong chi: ................."
    output.write(content.encode('utf-8'))
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"mau_{type}.txt", mimetype="text/plain")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
