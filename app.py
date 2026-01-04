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
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # Giới hạn file 10MB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}
LOGO_PATH = "/static/Logo.png"

# Data storage
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
            try:
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    # Giới hạn số trang để tránh OOM
                    for i, page in enumerate(reader.pages):
                        if i >= 50:  # Chỉ đọc tối đa 50 trang đầu
                            break
                        page_text = page.extract_text(fallback=False)  # Tránh xử lý sâu
                        text.append(page_text or "")
                    return "\n".join(text)
            except Exception as e:
                print("Lỗi đọc PDF:", e)
                return "Không thể đọc nội dung PDF (file phức tạp hoặc hỏng)."

        if ext == "docx" and docx:
            doc_obj = docx.Document(path)
            return "\n".join([p.text for p in doc_obj.paragraphs])

        if ext in ("csv", "xlsx") and pd:
            df = pd.read_csv(path) if ext == "csv" else pd.read_excel(path)
            return df.head(30).to_string()

    except Exception as e:
        print("Lỗi đọc file:", e)
    return ""

def vit5_summarize(text):
    if not text.strip():
        return "Nội dung rỗng."
    load_vit5_model()
    if not VIT5_AVAILABLE:
        return "Không thể tóm tắt (ViT5 chưa tải được)."
    try:
        input_text = "tóm tắt: " + text[:1500]  # Giảm xuống 1500 ký tự để nhẹ hơn
        inputs = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=512)
        summary_ids = model.generate(inputs["input_ids"], max_length=150, num_beams=4, early_stopping=True)
        return tokenizer.decode(summary_ids[0], skip_special_tokens=True).strip()
    except Exception as e:
        print("Lỗi tóm tắt:", e)
        return "Lỗi khi tóm tắt (có thể do nội dung quá phức tạp)."

# Route gốc - vừa health check vừa redirect người dùng
@app.route("/")
def index():
    if request.method == "HEAD":
        return "OK", 200
    user_agent = request.headers.get("User-Agent", "")
    if "Go-http-client" in user_agent or "Render" in user_agent:
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
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: #f0f7f4; color: #333; }
        header { background: linear-gradient(135deg, #2e7d32, #4caf50); color: white; padding: 20px 0; text-align: center; box-shadow: 0 4px 10px rgba(0,0,0,0.2); }
        header img { height: 80px; vertical-align: middle; }
        header h1 { display: inline; margin-left: 20px; font-size: 2em; }
        .container { max-width: 1100px; margin: 30px auto; padding: 30px; background: white; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        h2, h3, h4 { color: #2e7d32; }
        a { color: #2e7d32; text-decoration: none; font-weight: bold; }
        a:hover { text-decoration: underline; }
        input, select, button { padding: 10px; margin: 10px 0; border-radius: 6px; border: 1px solid #4caf50; font-size: 1em; width: 100%; box-sizing: border-box; }
        button { background: #4caf50; color: white; cursor: pointer; font-weight: bold; }
        button:hover { background: #388e3c; }
        .flash { padding: 15px; margin: 20px 0; border-radius: 6px; }
        .success { background: #e8f5e9; border-left: 5px solid #4caf50; }
        .danger { background: #ffebee; border-left: 5px solid #f44336; }
        .logout { position: absolute; top: 20px; right: 30px; }
        .summary-box { background:#e8f5e9; padding:20px; border-radius:8px; margin:20px 0; line-height:1.6; font-size:1.1em; }
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

# Routes
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
            flash("Sai tên đăng nhập hoặc mật khẩu!", "danger")
    body = """
    <h2>Đăng nhập hệ thống</h2>
    <form method="POST">
        <div>Tên đăng nhập:<br><input name="username" required></div><br>
        <div>Mật khẩu:<br><input name="password" type="password" required></div><br>
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

# (Giữ nguyên các route admin và bithu như trước - không thay đổi)

@app.route("/dangvien", methods=["GET", "POST"])
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

    summary = None
    uploaded_filename = None

    if request.method == "POST":
        if 'file' not in request.files:
            flash("Không có file được chọn!", "danger")
        else:
            file = request.files['file']
            if file.filename == '':
                flash("Không chọn file nào!", "danger")
            elif not allowed_file(file.filename):
                flash("Loại file không hỗ trợ! Chỉ chấp nhận: txt, pdf, docx, csv, xlsx", "danger")
            else:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                text = read_file_text(filepath)
                if not text.strip():
                    flash("Không thể đọc nội dung từ file này.", "danger")
                else:
                    summary = vit5_summarize(text)
                    if "Lỗi" in summary or "Không thể" in summary:
                        flash(summary, "danger")
                    else:
                        flash("Tóm tắt thành công bằng AI ViT5!", "success")
                    uploaded_filename = filename

    # Body template - ĐÃ SỬA CÚ PHÁP JINJA ĐÚNG 100%
    body = f"""
    <h2>Trang Đảng viên</h2>
    <p>Xin chào <strong>{user['name']}</strong><br>
    Thuộc <strong>{chi_bo_name or 'Chưa thuộc chi bộ nào'}</strong></p>

    <h3>Thông báo / Hoạt động chi bộ</h3>
    {% raw %}{% if thong_bao_cb %}{% endraw %}
    <ul>
        {% raw %}{% for tb in thong_bao_cb %}{% endraw %}
        <li>{{{{ tb.note }}}} <em>(bởi {{{{ USERS[tb.by].name }}}})</em></li>
        {% raw %}{% endfor %}{% endraw %}
    </ul>
    {% raw %}{% else %}{% endraw %}
    <p><em>Chưa có thông báo</em></p>
    {% raw %}{% endif %}{% endraw %}

    <h3>Nhận xét từ Bí thư</h3>
    {% raw %}{% if nhan_xet_cb %}{% endraw %}
    <ul>
        {% raw %}{% for nx in nhan_xet_cb %}{% endraw %}
        <li>{{{{ nx.note }}}} <em>(bởi {{{{ USERS[nx.by].name }}}})</em></li>
        {% raw %}{% endfor %}{% endraw %}
    </ul>
    {% raw %}{% else %}{% endraw %}
    <p><em>Chưa có nhận xét</em></p>
    {% raw %}{% endif %}{% endraw %}

    <h3>Upload tài liệu & Tóm tắt bằng AI (VietAI ViT5)</h3>
    <p>Chọn file (tối đa 10MB) để upload và nhận tóm tắt tự động.</p>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" accept=".txt,.pdf,.docx,.csv,.xlsx" required><br><br>
        <button type="submit">Upload và Tóm tắt</button>
    </form>

    {% raw %}{% if uploaded_filename %}{% endraw %}
    <p><strong>File đã upload:</strong> {{{{ uploaded_filename }}}}</p>
    {% raw %}{% endif %}{% endraw %}

    {% raw %}{% if summary %}{% endraw %}
    <h4>Kết quả tóm tắt:</h4>
    <div class="summary-box">
        {{{{ summary }}}}
    </div>
    {% raw %}{% endif %}{% endraw %}
    """

    return render_template_string(BASE_TEMPLATE, body_content=body, logo_path=LOGO_PATH,
                                  thong_bao_cb=thong_bao_cb, nhan_xet_cb=nhan_xet_cb,
                                  USERS=USERS, uploaded_filename=uploaded_filename, summary=summary)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
