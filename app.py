import os
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template_string, session, flash, abort
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
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), "uploads")
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # Giới hạn 8MB để an toàn
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}
LOGO_PATH = "/static/Logo.png"

# Data in-memory
USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Bí thư Chi bộ"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Đảng viên 01"},
}
NHAN_XET = {}
THONG_BAO = {}
CHI_BO_LIST = {
    "cb01": {"name": "Chi bộ 1", "users": ["dv01"]},
    "cb02": {"name": "Chi bộ 2", "users": []},
}

# Utilities
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

def read_file_text(path):
    ext = path.rsplit(".", 1)[1].lower()
    try:
        if ext == "txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                return content[:8000] if content else "File rỗng."

        if ext == "pdf" and PyPDF2:
            try:
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    if reader.is_encrypted:
                        return "PDF được mã hóa, không thể đọc."
                    text_parts = []
                    for i, page in enumerate(reader.pages):
                        if i >= 15:  # Chỉ đọc tối đa 15 trang đầu
                            break
                        try:
                            page_text = page.extract_text(fallback=False) or ""
                            text_parts.append(page_text)
                        except:
                            text_parts.append("[Không đọc được trang này]")
                    full_text = "\n".join(text_parts)
                    return full_text[:8000] or "Không đọc được nội dung PDF."
            except Exception as e:
                print("PDF error:", e)
                return "File PDF quá phức tạp hoặc bị hỏng, không thể đọc."

        if ext == "docx" and docx:
            doc_obj = docx.Document(path)
            paragraphs = [p.text for p in doc_obj.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)[:8000] or "File DOCX rỗng."

        if ext in ("csv", "xlsx") and pd:
            df = pd.read_csv(path) if ext == "csv" else pd.read_excel(path)
            return df.head(20).to_string()

    except Exception as e:
        print("Lỗi đọc file:", e)
        return "Lỗi khi đọc file."

    return "Không hỗ trợ định dạng này hoặc file rỗng."

# Route gốc
@app.route("/")
def index():
    if request.method == "HEAD":
        return "OK", 200
    if "Go-http-client" in request.headers.get("User-Agent", "") or "Render" in request.headers.get("User-Agent", ""):
        return "OK", 200
    return redirect(url_for("login"))

# Base template
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hệ thống Quản lý Đảng viên</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; margin:0; padding:0; background:#f0f7f4; color:#333; }
        header { background:linear-gradient(135deg,#2e7d32,#4caf50); color:white; padding:20px 0; text-align:center; box-shadow:0 4px 10px rgba(0,0,0,0.2); }
        header img { height:80px; vertical-align:middle; }
        header h1 { display:inline; margin-left:20px; font-size:2em; }
        .container { max-width:1100px; margin:30px auto; padding:30px; background:white; border-radius:12px; box-shadow:0 5px 15px rgba(0,0,0,0.1); }
        h2,h3,h4 { color:#2e7d32; }
        .flash { padding:15px; margin:20px 0; border-radius:6px; }
        .success { background:#e8f5e9; border-left:5px solid #4caf50; }
        .danger { background:#ffebee; border-left:5px solid #f44336; }
        .info { background:#e3f2fd; border-left:5px solid #2196f3; }
        .content-box { background:#f8fff8; padding:20px; border-radius:8px; margin:20px 0; white-space:pre-wrap; line-height:1.6; }
        .logout { position:absolute; top:20px; right:30px; }
        button { background:#4caf50; color:white; padding:10px; border:none; border-radius:6px; cursor:pointer; font-weight:bold; }
        button:hover { background:#388e3c; }
        input[type=file] { padding:10px; }
    </style>
</head>
<body>
    <header>
        <img src="{{ logo_path }}" alt="Logo">
        <h1>HỆ THỐNG QUẢN LÝ ĐẢNG VIÊN</h1>
        {% if session.user %}
        <div class="logout"><a href="{{ url_for('logout') }}" style="color:white;">Đăng xuất ({{ session.user.name }})</a></div>
        {% endif %}
    </header>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {{ body_content | safe }}
        <br><br>
        <a href="{{ url_for('dashboard') }}">← Về trang chủ</a>
    </div>
</body>
</html>
"""

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = USERS.get(username)
        if user and check_password_hash(user["password"], password):
            session["user"] = {"username": username, "role": user["role"], "name": user["name"]}
            flash("Đăng nhập thành công!", "success")
            return redirect(url_for("dashboard"))
        flash("Sai tên đăng nhập hoặc mật khẩu!", "danger")
    body = """
    <h2>Đăng nhập hệ thống</h2>
    <form method="POST">
        Tên đăng nhập:<br><input name="username" required style="width:300px;padding:10px;"><br><br>
        Mật khẩu:<br><input name="password" type="password" required style="width:300px;padding:10px;"><br><br>
        <button type="submit">Đăng nhập</button>
    </form>
    """
    return render_template_string(BASE_TEMPLATE, body_content=body, logo_path=LOGO_PATH)

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

@app.route("/dangvien", methods=["GET", "POST"])
@login_required("dangvien")
def dangvien_home():
    user = session["user"]
    chi_bo_name = "Chưa thuộc chi bộ nào"
    chi_bo_id = None
    for cb_id, cb in CHI_BO_LIST.items():
        if user["username"] in cb["users"]:
            chi_bo_name = cb["name"]
            chi_bo_id = cb_id
            break

    thong_bao_cb = THONG_BAO.get(chi_bo_id, [])
    nhan_xet_cb = NHAN_XET.get(user["username"], [])

    extracted_text = None
    uploaded_filename = None

    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Chưa chọn file!", "danger")
        elif not allowed_file(file.filename):
            flash("Chỉ hỗ trợ txt, pdf, docx, csv, xlsx!", "danger")
        else:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            extracted_text = read_file_text(filepath)
            uploaded_filename = filename
            if "không thể đọc" in extracted_text.lower() or "lỗi" in extracted_text.lower():
                flash(extracted_text, "danger")
            else:
                flash("Đọc nội dung file thành công!", "success")

    body = """
    <h2>Trang Đảng viên</h2>
    <p>Xin chào <strong>{{ user.name }}</strong><br>
    Thuộc <strong>{{ chi_bo_name }}</strong></p>

    <h3>Thông báo / Hoạt động chi bộ</h3>
    {% if thong_bao_cb %}
        <ul>
            {% for tb in thong_bao_cb %}
                <li>{{ tb.note }} <em>(bởi {{ USERS[tb.by].name }})</em></li>
            {% endfor %}
        </ul>
    {% else %}
        <p><em>Chưa có thông báo</em></p>
    {% endif %}

    <h3>Nhận xét từ Bí thư</h3>
    {% if nhan_xet_cb %}
        <ul>
            {% for nx in nhan_xet_cb %}
                <li>{{ nx.note }} <em>(bởi {{ USERS[nx.by].name }})</em></li>
            {% endfor %}
        </ul>
    {% else %}
        <p><em>Chưa có nhận xét</em></p>
    {% endif %}

    <h3>Upload tài liệu</h3>
    <p>Upload file để xem nội dung. (Tóm tắt AI tạm thời chưa hỗ trợ trên bản miễn phí)</p>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" accept=".txt,.pdf,.docx,.csv,.xlsx" required><br><br>
        <button type="submit">Upload & Xem nội dung</button>
    </form>

    {% if uploaded_filename %}
        <h4>File đã upload: <strong>{{ uploaded_filename }}</strong></h4>
        {% if extracted_text %}
            <div class="content-box">{{ extracted_text }}</div>
        {% endif %}
    {% endif %}
    """

    return render_template_string(
        BASE_TEMPLATE,
        body_content=body,
        logo_path=LOGO_PATH,
        user=user,
        chi_bo_name=chi_bo_name,
        thong_bao_cb=thong_bao_cb,
        nhan_xet_cb=nhan_xet_cb,
        USERS=USERS,
        uploaded_filename=uploaded_filename,
        extracted_text=extracted_text
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
