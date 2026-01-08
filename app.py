import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import io

# Tùy chọn xử lý file
try:
    import PyPDF2
    import docx
    import pandas as pd
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-2026")
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}

# --- DỮ LIỆU IN-MEMORY (Sẽ mất khi restart server) ---
USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Nguyễn Văn Bí Thư"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Trần Văn Đảng Viên"},
}

# Lưu vết chi bộ: {chi_bo_id: {name: "...", users: [username1, ...]}}
CHI_BO_LIST = {
    "cb01": {"name": "Chi bộ Khối Văn phòng", "users": ["bithu1", "dv01"]},
    "cb02": {"name": "Chi bộ Kỹ thuật", "users": []},
}

NHAN_XET = {}  # {target_user: [{"by": author, "note": "..."}]}
THONG_BAO = {} # {chi_bo_id: [{"by": author, "note": "..."}]}

# --- DECORATORS ---
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

# --- UTILITIES ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def ai_summarize(text):
    """Giả lập hàm tóm tắt văn bản bằng AI chuyên nghiệp"""
    if not text or len(text) < 50: return text
    return f"[AI SUMMARY]: Văn bản này tập trung vào các vấn đề cốt lõi: 1. Đánh giá tình hình thực hiện nhiệm vụ; 2. Phân tích các ưu khuyết điểm tồn tại; 3. Đề xuất giải pháp khắc phục và phương hướng hành động trong thời gian tới. Nội dung mang tính xây dựng và có chiều sâu chính trị."

def read_file_text(path):
    ext = path.rsplit(".", 1)[1].lower()
    try:
        if ext == "txt":
            with open(path, "r", encoding="utf-8") as f: return f.read()[:5000]
        if ext == "pdf":
            reader = PyPDF2.PdfReader(path)
            return " ".join([p.extract_text() for p in reader.pages[:5]])
        if ext == "docx":
            doc = docx.Document(path)
            return " ".join([p.text for p in doc.paragraphs])
        if ext in ("csv", "xlsx"):
            return "Dữ liệu bảng tính (đã nhận dạng)."
    except:
        return "Lỗi đọc định dạng file."
    return ""

# --- ROUTES ---
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        user = USERS.get(u)
        if user and check_password_hash(user["password"], p):
            session["user"] = {"username": u, "role": user["role"], "name": user["name"]}
            flash("Chào mừng bạn quay trở lại!", "success")
            return redirect(url_for("dashboard"))
        flash("Sai tài khoản hoặc mật khẩu!", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["user"]["role"]
    return redirect(url_for(f"{role}_home" if role != "admin" else "admin_users"))

# --- ADMIN ROUTES ---
@app.route("/admin/users")
@login_required("admin")
def admin_users():
    return render_template("admin.html", USERS=USERS, CHI_BO_LIST=CHI_BO_LIST)

@app.route("/admin/add_user", methods=["POST"])
@login_required("admin")
def admin_add_user():
    username = request.form["username"].strip()
    if username in USERS:
        flash("Username đã tồn tại!", "danger")
    else:
        USERS[username] = {
            "password": generate_password_hash(request.form["password"]),
            "role": request.form["role"],
            "name": request.form["name"]
        }
        cb_id = request.form.get("chi_bo_id")
        if cb_id: CHI_BO_LIST[cb_id]["users"].append(username)
        flash(f"Đã tạo tài khoản {username}", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/reset/<username>")
@login_required("admin")
def admin_reset_pw(username):
    if username in USERS:
        USERS[username]["password"] = generate_password_hash("Test@123")
        flash(f"Đã đặt lại mật khẩu cho {username} về Test@123", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/delete/<username>")
@login_required("admin")
def admin_delete(username):
    if username == "admin": flash("Không thể xóa Admin!", "danger")
    else:
        USERS.pop(username, None)
        for cb in CHI_BO_LIST.values():
            if username in cb["users"]: cb["users"].remove(username)
        flash("Đã xóa người dùng.", "success")
    return redirect(url_for("admin_users"))

@app.route("/admin/move", methods=["POST"])
@login_required("admin")
def admin_move_user():
    u, to_cb = request.form["username"], request.form["to_cb"]
    for cb in CHI_BO_LIST.values():
        if u in cb["users"]: cb["users"].remove(u)
    CHI_BO_LIST[to_cb]["users"].append(u)
    flash(f"Đã chuyển {u} sang {CHI_BO_LIST[to_cb]['name']}", "success")
    return redirect(url_for("admin_users"))

# --- ROLE ROUTES ---
@app.route("/bithu", methods=["GET", "POST"])
@login_required("bithu")
def bithu_home():
    username = session["user"]["username"]
    cb_id = next((k for k, v in CHI_BO_LIST.items() if username in v["users"]), None)
    if not cb_id: return "Bạn chưa được phân vào chi bộ nào!"
    
    if request.method == "POST":
        target = request.form.get("dv_username")
        note = request.form.get("nhan_xet")
        msg = request.form.get("thong_bao")
        if target and note:
            NHAN_XET.setdefault(target, []).append({"by": username, "note": note})
        if msg:
            THONG_BAO.setdefault(cb_id, []).append({"by": username, "note": msg})
        flash("Đã gửi nội dung!", "success")

    return render_template("bithu.html", user=session["user"], 
                           members=CHI_BO_LIST[cb_id]["users"], 
                           USERS=USERS, cb_id=cb_id, THONG_BAO=THONG_BAO)

@app.route("/dangvien")
@login_required("dangvien")
def dangvien_home():
    u = session["user"]["username"]
    cb_id = next((k for k, v in CHI_BO_LIST.items() if u in v["users"]), None)
    my_nx = NHAN_XET.get(u, [])
    my_tb = THONG_BAO.get(cb_id, []) if cb_id else []
    return render_template("dangvien.html", user=session["user"], reviews=my_nx, notices=my_tb)

# --- AI & TEMPLATES ---
@app.route("/upload", methods=["POST"])
@login_required()
def process_ai():
    file = request.files.get("file")
    if file and allowed_file(file.filename):
        path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
        file.save(path)
        raw_text = read_file_text(path)
        summary = ai_summarize(raw_text)
        return render_template("ai_result.html", summary=summary)
    flash("File không hợp lệ!", "danger")
    return redirect(url_for("dashboard"))

@app.route("/download/<type>")
@login_required()
def download_template(type):
    # Giả lập tạo file docx mẫu
    output = io.BytesIO()
    output.write(f"MAU BAN TU NHAN XET - {type.upper()}\nHo ten:........\nNoi dung:........".encode('utf-8'))
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"mau_nhan_xet_{type}.txt", mimetype="text/plain")

if __name__ == "__main__":
    app.run(debug=True)
