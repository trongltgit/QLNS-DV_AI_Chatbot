import os
import re
import unicodedata
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template_string, session, flash, abort, send_from_directory
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

# OpenAI
try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_CLIENT = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    OPENAI_AVAILABLE = bool(OPENAI_CLIENT)
except:
    OPENAI_CLIENT = None
    OPENAI_AVAILABLE = False

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-2025")
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}
LOGO_PATH = "/static/Logo.png"

# -------------------------
# Data storage
# -------------------------
USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Bí thư Chi bộ"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Đảng viên 01"},
}

DOCS = {}  # key=username, value=list of uploaded file info
CHAT_HISTORY = {}
NHAN_XET = {}  # key=username, value=list of nhận xét
THONG_BAO = {}  # key=chi_bo_id, value=list of thông báo/hoạt động
SINH_HOAT = []

# Chi bộ
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

def normalize_vietnamese(text):
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return " ".join(text.split())

def read_file_text(path):
    ext = path.rsplit(".",1)[1].lower()
    try:
        if ext=="txt":
            with open(path,"r",encoding="utf-8",errors="ignore") as f: return f.read()
        if ext=="pdf" and PyPDF2:
            text=[]
            with open(path,"rb") as f:
                reader=PyPDF2.PdfReader(f)
                for page in reader.pages:
                    t = page.extract_text() or ""
                    text.append(t)
            return "\n".join(text)
        if ext=="docx" and docx:
            doc_obj = docx.Document(path)
            return "\n".join([p.text for p in doc_obj.paragraphs])
        if ext in ("csv","xlsx") and pd:
            df = pd.read_csv(path) if ext=="csv" else pd.read_excel(path)
            return df.head(30).to_string()
    except:
        return ""
    return ""

def openai_summarize(text):
    if not OPENAI_AVAILABLE or not text.strip():
        return "Không thể tóm tắt (thiếu OpenAI hoặc nội dung rỗng)."
    resp = OPENAI_CLIENT.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":"Tóm tắt ngắn gọn nội dung sau:\n\n"+text}],
        max_tokens=200
    )
    return resp.choices[0].message.content.strip()

# -------------------------
# Routes: Auth
# -------------------------
@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = USERS.get(username)
        if user and check_password_hash(user["password"], password):
            session["user"] = {"username": username, "role": user["role"], "name": user["name"]}
            flash("Đăng nhập thành công!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Sai username hoặc password!", "danger")
    return render_template_string("""
    <html><head><title>Login</title></head>
    <body>
    <h2>Đăng nhập hệ thống</h2>
    {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
    <p style="color:red">{{ msg }}</p>
    {% endfor %}
    {% endwith %}
    <form method="POST">
        Username: <input name="username"><br>
        Password: <input name="password" type="password"><br>
        <button type="submit">Login</button>
    </form>
    </body></html>
    """)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -------------------------
# Dashboard
# -------------------------
@app.route("/dashboard")
@login_required()
def dashboard():
    user = session["user"]
    role = user["role"]
    if role=="admin":
        return redirect(url_for("admin_users"))
    elif role=="bithu":
        return redirect(url_for("bithu_home"))
    else:
        return redirect(url_for("dangvien_home"))

# -------------------------
# Admin: Users
# -------------------------
@app.route("/admin/users")
@admin_required
def admin_users():
    return render_template_string("""
    <h2>Quản lý Users</h2>
    <a href="{{ url_for('admin_add_user') }}">Thêm user mới</a><br><br>
    <table border=1>
    <tr><th>Username</th><th>Họ tên</th><th>Role</th><th>Chi bộ</th></tr>
    {% for u,p in USERS.items() %}
        <tr>
        <td>{{u}}</td>
        <td>{{p.name}}</td>
        <td>{{p.role}}</td>
        <td>
            {% for cb_id, cb in CHI_BO_LIST.items() %}
                {% if u in cb.users %}{{cb.name}}{% endif %}
            {% endfor %}
        </td>
        </tr>
    {% endfor %}
    </table>
    """, USERS=USERS, CHI_BO_LIST=CHI_BO_LIST)

@app.route("/admin/add_user", methods=["GET","POST"])
@admin_required
def admin_add_user():
    if request.method=="POST":
        username = request.form.get("username").strip()
        name = request.form.get("name").strip()
        password = request.form.get("password").strip() or "Test@123"
        role = request.form.get("role")
        chi_bo_id = request.form.get("chi_bo_id")  # gán chi bộ khi tạo user

        if username in USERS:
            flash("User đã tồn tại!", "danger")
            return redirect(url_for("admin_add_user"))

        USERS[username] = {"password": generate_password_hash(password), "role": role, "name": name}

        if chi_bo_id and chi_bo_id in CHI_BO_LIST:
            CHI_BO_LIST[chi_bo_id]["users"].append(username)

        flash(f"Thêm user {username} thành công!", "success")
        return redirect(url_for("admin_users"))
    
    return render_template_string("""
    <h2>Thêm User</h2>
    <form method="POST">
        Username: <input name="username"><br>
        Họ tên: <input name="name"><br>
        Password: <input name="password" placeholder="Mặc định Test@123"><br>
        Role: <select name="role">
            <option value="dangvien">Đảng viên</option>
            <option value="bithu">Bí thư chi bộ</option>
        </select><br>
        Chi bộ: <select name="chi_bo_id">
            <option value="">--Chọn--</option>
            {% for cb_id, cb in CHI_BO_LIST.items() %}
            <option value="{{cb_id}}">{{cb['name']}}</option>
            {% endfor %}
        </select><br>
        <button type="submit">Thêm user</button>
    </form>
    """, CHI_BO_LIST=CHI_BO_LIST)

# -------------------------
# Bí thư chi bộ
# -------------------------
@app.route("/bithu", methods=["GET","POST"])
@login_required("bithu")
def bithu_home():
    user = session["user"]
    chi_bo_users = []
    chi_bo_id = ""
    for cb_id, cb in CHI_BO_LIST.items():
        if user["username"] in cb["users"]:
            chi_bo_users = cb["users"]
            chi_bo_id = cb_id
            break

    if request.method=="POST":
        # Nhận xét đảng viên
        dv_username = request.form.get("dv_username")
        nhan_xet = request.form.get("nhan_xet")
        if dv_username not in NHAN_XET:
            NHAN_XET[dv_username] = []
        NHAN_XET[dv_username].append({"by": user["username"], "note": nhan_xet})
        # Thông báo chi bộ
        thong_bao = request.form.get("thong_bao")
        if thong_bao:
            if chi_bo_id not in THONG_BAO:
                THONG_BAO[chi_bo_id] = []
            THONG_BAO[chi_bo_id].append({"by": user["username"], "note": thong_bao})
        flash("Cập nhật thành công!", "success")
        return redirect(url_for("bithu_home"))

    return render_template_string("""
    <h2>Trang Bí thư Chi bộ</h2>
    <p>Xin chào {{user.name}}</p>

    <h3>Đảng viên trong chi bộ</h3>
    <ul>
    {% for u in chi_bo_users %}
        <li>{{USERS[u].name}} ({{u}})</li>
        <ul>
        {% if NHAN_XET.get(u) %}
            {% for nx in NHAN_XET[u] %}
            <li>Nhận xét: {{nx.note}} (bởi {{USERS[nx.by].name}})</li>
            {% endfor %}
        {% endif %}
        </ul>
    {% endfor %}
    </ul>

    <h3>Thêm nhận xét hoặc thông báo</h3>
    <form method="POST">
        Nhận xét đảng viên: 
        <select name="dv_username">
            {% for u in chi_bo_users %}
                <option value="{{u}}">{{USERS[u].name}} ({{u}})</option>
            {% endfor %}
        </select><br>
        Nội dung nhận xét: <input name="nhan_xet"><br>
        Thông báo chi bộ: <input name="thong_bao"><br>
        <button type="submit">Gửi</button>
    </form>

    <h3>Thông báo/hoạt động chi bộ</h3>
    <ul>
    {% if THONG_BAO.get(chi_bo_id) %}
        {% for tb in THONG_BAO[chi_bo_id] %}
            <li>{{tb.note}} (bởi {{USERS[tb.by].name}})</li>
        {% endfor %}
    {% endif %}
    </ul>
    """, user=user, chi_bo_users=chi_bo_users, USERS=USERS, NHAN_XET=NHAN_XET, THONG_BAO=THONG_BAO, chi_bo_id=chi_bo_id)

# -------------------------
# Đảng viên
# -------------------------
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
    return render_template_string("""
    <h2>Trang Đảng viên</h2>
    <p>Xin chào {{user.name}} (Chi bộ: {{chi_bo_name}})</p>

    <h3>Thông báo/hoạt động chi bộ</h3>
    <ul>
    {% for tb in thong_bao_cb %}
        <li>{{tb.note}} (bởi {{USERS[tb.by].name}})</li>
    {% endfor %}
    </ul>

    <h3>Nhận xét của Bí thư</h3>
    <ul>
    {% for nx in nhan_xet_cb %}
        <li>{{nx.note}} (bởi {{USERS[nx.by].name}})</li>
    {% endfor %}
    </ul>
    """, user=user, chi_bo_name=chi_bo_name, thong_bao_cb=thong_bao_cb, nhan_xet_cb=nhan_xet_cb, USERS=USERS)

# -------------------------
# Run
# -------------------------
if __name__=="__main__":
    app.run(debug=True)
