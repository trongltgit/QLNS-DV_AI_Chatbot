import os
import re
import unicodedata
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template_string, session, flash, abort

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Optional dependencies
try:
    import PyPDF2
except:
    PyPDF2 = None
try:
    import docx
except:
    docx = None
try:
    import pandas as pd
except:
    pd = None

# VietAI ViT5 - Lazy loading
VIT5_AVAILABLE = False
tokenizer = None
model = None

def load_vit5_model():
    global tokenizer, model, VIT5_AVAILABLE
    if VIT5_AVAILABLE:
        return
    try:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        print("Đang tải VietAI ViT5 model... (có thể mất 1-2 phút lần đầu)")
        tokenizer = AutoTokenizer.from_pretrained("VietAI/vit5-base")
        model = AutoModelForSeq2SeqLM.from_pretrained("VietAI/vit5-base")
        VIT5_AVAILABLE = True
        print("ViT5 model tải thành công!")
    except Exception as e:
        print("Không tải được VietAI ViT5:", str(e))
        VIT5_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-2025")

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}
LOGO_PATH = "/static/Logo.png"

# -------------------------
# Data storage (in-memory - sẽ mất khi restart)
# -------------------------
USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Bí thư Chi bộ"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Đảng viên 01"},
}

DOCS = {}
NHAN_XET = {}
THONG_BAO = {}

CHI_BO_LIST = {
    "cb01": {"name": "Chi bộ 1", "users": ["dv01"]},
    "cb02": {"name": "Chi bộ 2", "users": []},
}

# -------------------------
# Utilities
# -------------------------
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

def admin_required(fn):
    return login_required("admin")(fn)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def read_file_text(path):
    ext = path.rsplit(".", 1)[1].lower()
    try:
        if ext == "txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if ext == "pdf" and PyPDF2:
            text = []
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    t = page.extract_text() or ""
                    text.append(t)
            return "\n".join(text)
        if ext == "docx" and docx:
            doc_obj = docx.Document(path)
            return "\n".join([p.text for p in doc_obj.paragraphs])
        if ext in ("csv", "xlsx") and pd:
            df = pd.read_csv(path) if ext == "csv" else pd.read_excel(path)
            return df.head(30).to_string()
    except Exception as e:
        print("Lỗi đọc file:", e)
        return ""
    return ""

def vit5_summarize(text):
    if not text.strip():
        return "Nội dung rỗng."

    load_vit5_model()  # Lazy load

    if not VIT5_AVAILABLE:
        return "Không thể tóm tắt (ViT5 không khả dụng hoặc đang tải)."

    try:
        input_text = "tóm tắt: " + text[:2000]
        inputs = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=512)
        summary_ids = model.generate(
            inputs["input_ids"],
            max_length=200,
            num_beams=4,
            early_stopping=True
        )
        summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        return summary.strip()
    except Exception as e:
        print("Lỗi khi tóm tắt:", e)
        return "Lỗi khi tóm tắt văn bản."

# -------------------------
# Health check route (rất quan trọng cho Render)
# -------------------------
@app.route("/")
def health():
    return "OK", 200

# -------------------------
# Base template
# -------------------------
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hệ thống Quản lý Đảng viên</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f0f7f4; color: #333; }
        header { background: linear-gradient(135deg, #2e7d32, #4caf50); color: white; padding: 20px 0; text-align: center; box-shadow: 0 4px 10px rgba(0,0,0,0.2); }
        header img { height: 80px; vertical-align: middle; }
        header h1 { display: inline; margin-left: 20px; font-size: 2em; }
        .container { max-width: 1100px; margin: 30px auto; padding: 30px; background: white; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); text-align: center; }
        h2, h3 { color: #2e7d32; }
        a { color: #2e7d32; text-decoration: none; font-weight: bold; }
        a:hover { text-decoration: underline; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        table, th, td { border: 1px solid #4caf50; }
        th { background: #4caf50; color: white; padding: 12px; }
        td { padding: 10px; }
        input, select, button { padding: 10px; margin: 10px; border-radius: 6px; border: 1px solid #4caf50; font-size: 1em; }
        button { background: #4caf50; color: white; cursor: pointer; font-weight: bold; }
        button:hover { background: #388e3c; }
        .flash { padding: 15px; margin: 20px 0; border-radius: 6px; }
        .success { background: #e8f5e9; border-left: 5px solid #4caf50; }
        .danger { background: #ffebee; border-left: 5px solid #f44336; }
        ul { text-align: left; display: inline-block; }
        .logout { position: absolute; top: 20px; right: 30px; }
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
        {{ body_content|safe }}
        <br><br>
        <a href="{{ url_for('dashboard') }}">← Về trang chủ</a>
    </div>
</body>
</html>
"""

# -------------------------
# Routes
# -------------------------
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
        else:
            flash("Sai username hoặc password!", "danger")
    body = """
    <h2>Đăng nhập hệ thống</h2>
    <form method="POST">
        <div>Tên đăng nhập:<br><input name="username" required style="width:300px;"></div><br>
        <div>Mật khẩu:<br><input name="password" type="password" required style="width:300px;"></div><br>
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
    user = session["user"]
    if user["role"] == "admin":
        return redirect(url_for("admin_users"))
    elif user["role"] == "bithu":
        return redirect(url_for("bithu_home"))
    else:
        return redirect(url_for("dangvien_home"))

@app.route("/admin/users")
@admin_required
def admin_users():
    body = """
    <h2>Quản lý Người dùng</h2>
    <a href="{{ url_for('admin_add_user') }}">➕ Thêm người dùng mới</a><br><br>
    <table>
        <tr><th>Username</th><th>Họ tên</th><th>Vai trò</th><th>Chi bộ</th></tr>
        {% for u, p in USERS.items() %}
        <tr>
            <td>{{ u }}</td>
            <td>{{ p.name }}</td>
            <td>{{ p.role }}</td>
            <td>{% for cb_id, cb in CHI_BO_LIST.items() %}{% if u in cb.users %}{{ cb.name }}{% endif %}{% endfor %}</td>
        </tr>
        {% endfor %}
    </table>
    """
    return render_template_string(BASE_TEMPLATE, body_content=body, logo_path=LOGO_PATH, USERS=USERS, CHI_BO_LIST=CHI_BO_LIST)

@app.route("/admin/add_user", methods=["GET", "POST"])
@admin_required
def admin_add_user():
    if request.method == "POST":
        username = request.form.get("username").strip()
        name = request.form.get("name").strip()
        password = request.form.get("password").strip() or "Test@123"
        role = request.form.get("role")
        chi_bo_id = request.form.get("chi_bo_id")
        if username in USERS:
            flash("User đã tồn tại!", "danger")
            return redirect(url_for("admin_add_user"))
        USERS[username] = {"password": generate_password_hash(password), "role": role, "name": name}
        if chi_bo_id and chi_bo_id in CHI_BO_LIST:
            CHI_BO_LIST[chi_bo_id]["users"].append(username)
        flash(f"Thêm user {username} thành công!", "success")
        return redirect(url_for("admin_users"))
    body = """
    <h2>Thêm Người dùng mới</h2>
    <form method="POST">
        <div>Username:<br><input name="username" required></div>
        <div>Họ tên:<br><input name="name" required></div>
        <div>Mật khẩu (để trống dùng Test@123):<br><input name="password" type="password"></div>
        <div>Vai trò:<br><select name="role">
            <option value="dangvien">Đảng viên</option>
            <option value="bithu">Bí thư chi bộ</option>
        </select></div>
        <div>Chi bộ:<br><select name="chi_bo_id">
            <option value="">--Không chọn--</option>
            {% for cb_id, cb in CHI_BO_LIST.items() %}
            <option value="{{ cb_id }}">{{ cb.name }}</option>
            {% endfor %}
        </select></div><br>
        <button type="submit">Thêm người dùng</button>
    </form>
    """
    return render_template_string(BASE_TEMPLATE, body_content=body, logo_path=LOGO_PATH, CHI_BO_LIST=CHI_BO_LIST)

@app.route("/bithu", methods=["GET", "POST"])
@login_required("bithu")
def bithu_home():
    user = session["user"]
    chi_bo_users = []
    chi_bo_id = ""
    chi_bo_name = ""
    for cb_id, cb in CHI_BO_LIST.items():
        if user["username"] in cb["users"]:
            chi_bo_users = cb["users"]
            chi_bo_id = cb_id
            chi_bo_name = cb["name"]
            break

    if request.method == "POST":
        dv_username = request.form.get("dv_username")
        nhan_xet = request.form.get("nhan_xet")
        if dv_username and nhan_xet:
            NHAN_XET.setdefault(dv_username, []).append({"by": user["username"], "note": nhan_xet})
        thong_bao = request.form.get("thong_bao")
        if thong_bao:
            THONG_BAO.setdefault(chi_bo_id, []).append({"by": user["username"], "note": thong_bao})
        flash("Cập nhật thành công!", "success")
        return redirect(url_for("bithu_home"))

    body = """
    <h2>Trang Bí thư Chi bộ</h2>
    <p>Xin chào <strong>{{ user.name }}</strong> - {{ chi_bo_name }}</p>
    <h3>Đảng viên trong chi bộ</h3>
    <ul>
    {% for u in chi_bo_users %}
        <li><strong>{{ USERS[u].name }} ({{ u }})</strong>
            <ul>
            {% for nx in NHAN_XET.get(u, []) %}
                <li>{{ nx.note }} <em>(bởi {{ USERS[nx.by].name }})</em></li>
            {% else %}
                <li><em>Chưa có nhận xét</em></li>
            {% endfor %}
            </ul>
        </li>
    {% endfor %}
    </ul>
    <h3>Thêm nhận xét hoặc thông báo</h3>
    <form method="POST">
        <div>Nhận xét cho:<br><select name="dv_username">
            {% for u in chi_bo_users %}
            <option value="{{ u }}">{{ USERS[u].name }} ({{ u }})</option>
            {% endfor %}
        </select></div>
        <div>Nội dung nhận xét:<br><input name="nhan_xet" style="width:500px;"></div>
        <div>Thông báo chi bộ:<br><input name="thong_bao" style="width:500px;"></div><br>
        <button type="submit">Gửi</button>
    </form>
    <h3>Thông báo chi bộ</h3>
    <ul>
    {% for tb in THONG_BAO.get(chi_bo_id, []) %}
        <li>{{ tb.note }} <em>(bởi {{ USERS[tb.by].name }})</em></li>
    {% else %}
        <li><em>Chưa có thông báo</em></li>
    {% endfor %}
    </ul>
    """
    return render_template_string(BASE_TEMPLATE, body_content=body, logo_path=LOGO_PATH,
                                  user=user, chi_bo_name=chi_bo_name, chi_bo_users=chi_bo_users,
                                  USERS=USERS, NHAN_XET=NHAN_XET, THONG_BAO=THONG_BAO, chi_bo_id=chi_bo_id)

@app.route("/dangvien")
@login_required("dangvien")
def dangvien_home():
    user = session["user"]
    chi_bo_name = ""
    chi_bo_id = ""
    for cb_id, cb in CHI_BO_LIST.items():
        if user["username"] in cb["users"]:
            chi_bo_name = cb["name"]
            chi_bo_id = cb_id
            break
    thong_bao_cb = THONG_BAO.get(chi_bo_id, [])
    nhan_xet_cb = NHAN_XET.get(user["username"], [])
    body = """
    <h2>Trang Đảng viên</h2>
    <p>Xin chào <strong>{{ user.name }}</strong><br>Thuộc <strong>{{ chi_bo_name }}</strong></p>
    <h3>Thông báo/Hoạt động chi bộ</h3>
    <ul>
    {% for tb in thong_bao_cb %}
        <li>{{ tb.note }} <em>(bởi {{ USERS[tb.by].name }})</em></li>
    {% else %}
        <li><em>Chưa có thông báo</em></li>
    {% endfor %}
    </ul>
    <h3>Nhận xét từ Bí thư</h3>
    <ul>
    {% for nx in nhan_xet_cb %}
        <li>{{ nx.note }} <em>(bởi {{ USERS[nx.by].name }})</em></li>
    {% else %}
        <li><em>Chưa có nhận xét</em></li>
    {% endfor %}
    </ul>
    """
    return render_template_string(BASE_TEMPLATE, body_content=body, logo_path=LOGO_PATH,
                                  user=user, chi_bo_name=chi_bo_name,
                                  thong_bao_cb=thong_bao_cb, nhan_xet_cb=nhan_xet_cb, USERS=USERS)

# Chỉ chạy local, không ảnh hưởng đến deploy trên Render
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
