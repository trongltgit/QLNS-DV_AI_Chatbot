import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Optional dependencies
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None
try:
    import docx
except ImportError:
    docx = None
try:
    import pandas as pd
except ImportError:
    pd = None

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-2025")
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # Giới hạn 8MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}

# In-memory data
USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Bí thư Chi bộ"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Đảng viên 01"},
}
NHAN_XET = {}  # {username_dv: [{"by": username_bithu, "note": "..."}, ...]}
THONG_BAO = {}  # {chi_bo_id: [{"by": username, "note": "..."}, ...]}
CHI_BO_LIST = {
    "cb01": {"name": "Chi bộ 1", "users": ["dv01"]},
    "cb02": {"name": "Chi bộ 2", "users": []},
}

# Decorators
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

# Utilities
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def read_file_text(path):
    ext = path.rsplit(".", 1)[1].lower()
    try:
        if ext == "txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:10000]
        if ext == "pdf" and PyPDF2:
            try:
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    text = []
                    for i in range(min(15, len(reader.pages))):
                        t = reader.pages[i].extract_text() or ""
                        text.append(t)
                    return "\n".join(text)[:10000]
            except:
                return "Không thể đọc nội dung PDF (file phức tạp hoặc bị hỏng)."
        if ext == "docx" and docx:
            d = docx.Document(path)
            return "\n".join([p.text for p in d.paragraphs if p.text.strip()])[:10000]
        if ext in ("csv", "xlsx") and pd:
            df = pd.read_csv(path) if ext == "csv" else pd.read_excel(path)
            return df.head(20).to_string()
    except Exception as e:
        print("Lỗi đọc file:", e)
        return "Lỗi khi xử lý file."
    return "File rỗng hoặc không hỗ trợ."

# Routes
@app.route("/")
def index():
    if request.method == "HEAD" or "Go-http-client" in request.headers.get("User-Agent", ""):
        return "OK", 200
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = USERS.get(username)
        if user and check_password_hash(user["password"], password):
            session["user"] = {"username": username, "role": user["role"], "name": user["name"]}
            flash("Đăng nhập thành công!", "success")
            return redirect(url_for("dashboard"))
        flash("Sai tên đăng nhập hoặc mật khẩu!", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["user"]["role"]
    if role == "admin":
        return redirect(url_for("admin_users"))
    elif role == "bithu":
        return redirect(url_for("bithu_home"))
    else:
        return redirect(url_for("dangvien_home"))

# Admin routes
@app.route("/admin/users")
@login_required("admin")
def admin_users():
    return render_template("admin.html", USERS=USERS, CHI_BO_LIST=CHI_BO_LIST)

@app.route("/admin/add_user", methods=["GET", "POST"])
@login_required("admin")
def admin_add_user():
    if request.method == "POST":
        username = request.form["username"].strip()
        name = request.form["name"].strip()
        password = request.form.get("password", "Test@123").strip()
        role = request.form["role"]
        chi_bo_id = request.form.get("chi_bo_id")

        if username in USERS:
            flash("Username đã tồn tại!", "danger")
        else:
            USERS[username] = {
                "password": generate_password_hash(password),
                "role": role,
                "name": name
            }
            if chi_bo_id:
                CHI_BO_LIST[chi_bo_id]["users"].append(username)
            flash(f"Thêm người dùng {username} thành công!", "success")
        return redirect(url_for("admin_users"))

    # Hiển thị form thêm user (tái sử dụng admin.html hoặc tách riêng sau)
    return render_template("admin.html", USERS=USERS, CHI_BO_LIST=CHI_BO_LIST, show_add_form=True)

# Bí thư chi bộ
@app.route("/bithu", methods=["GET", "POST"])
@login_required("bithu")
def bithu_home():
    user = session["user"]
    chi_bo = next((cb for cb in CHI_BO_LIST.values() if user["username"] in cb["users"]), None)
    if not chi_bo:
        flash("Bạn chưa thuộc chi bộ nào!", "danger")
        return redirect(url_for("dashboard"))

    chi_bo_name = chi_bo["name"]
    chi_bo_id = next((k for k, v in CHI_BO_LIST.items() if user["username"] in v["users"]), None)
    chi_bo_users = chi_bo["users"]

    if request.method == "POST":
        dv_username = request.form.get("dv_username")
        nhan_xet = request.form.get("nhan_xet", "").strip()
        thong_bao = request.form.get("thong_bao", "").strip()

        if dv_username and nhan_xet:
            NHAN_XET.setdefault(dv_username, []).append({"by": user["username"], "note": nhan_xet})
        if thong_bao:
            THONG_BAO.setdefault(chi_bo_id, []).append({"by": user["username"], "note": thong_bao})
        flash("Cập nhật thành công!", "success")
        return redirect(url_for("bithu_home"))

    return render_template("bithu.html",
                           user=user,
                           chi_bo_name=chi_bo_name,
                           chi_bo_id=chi_bo_id,
                           chi_bo_users=chi_bo_users,
                           USERS=USERS,
                           NHAN_XET=NHAN_XET,
                           THONG_BAO=THONG_BAO)

# Đảng viên
@app.route("/dangvien", methods=["GET", "POST"])
@login_required("dangvien")
def dangvien_home():
    user = session["user"]
    chi_bo = next((cb for cb in CHI_BO_LIST.values() if user["username"] in cb["users"]), None)
    chi_bo_name = chi_bo["name"] if chi_bo else "Chưa thuộc chi bộ nào"
    chi_bo_id = next((k for k, v in CHI_BO_LIST.items() if user["username"] in v["users"]), None)

    thong_bao_cb = THONG_BAO.get(chi_bo_id, [])
    nhan_xet_cb = NHAN_XET.get(user["username"], [])

    extracted_text = None
    uploaded_filename = None

    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Vui lòng chọn file!", "danger")
        elif not allowed_file(file.filename):
            flash("Chỉ hỗ trợ: txt, pdf, docx, csv, xlsx", "danger")
        else:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            extracted_text = read_file_text(filepath)
            uploaded_filename = filename
            if "không thể" in extracted_text.lower() or "lỗi" in extracted_text.lower():
                flash(extracted_text, "danger")
            else:
                flash("Đọc nội dung file thành công!", "success")

    return render_template("dangvien.html",
                           user=user,
                           chi_bo_name=chi_bo_name,
                           thong_bao_cb=thong_bao_cb,
                           nhan_xet_cb=nhan_xet_cb,
                           USERS=USERS,
                           uploaded_filename=uploaded_filename,
                           extracted_text=extracted_text)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
