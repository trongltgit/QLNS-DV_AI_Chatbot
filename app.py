import os
import re
import requests
import unicodedata
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    session, abort, send_from_directory, flash, get_flashed_messages, jsonify, send_file
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# --- Giả định cài đặt thư viện ---
# BẮT BUỘC: Bạn cần cài đặt thư viện reportlab nếu chưa có (pip install reportlab)
try:
    # Đăng ký font hỗ trợ tiếng Việt (Arial là font phổ biến)
    pdfmetrics.registerFont(TTFont('VietFont', 'static/Arial.ttf'))
    PDF_FONT_NAME = 'VietFont'
except Exception:
    # Fallback nếu không tìm thấy static/Arial.ttf
    PDF_FONT_NAME = 'Helvetica'
    print("WARNING: Không tìm thấy static/Arial.ttf. Sử dụng font Helvetica mặc định.")
# --- End Giả định ---

# Optional dependencies (Duy trì cấu trúc ban đầu)
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except Exception:
    FIRESTORE_AVAILABLE = False
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    import docx
except Exception:
    docx = None
try:
    import pandas as pd
except Exception:
    pd = None

# Cập nhật cách khởi tạo OpenAI Client
try:
    import openai
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_CLIENT = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    OPENAI_AVAILABLE = bool(OPENAI_CLIENT)
except Exception:
    openai = None
    OPENAI_CLIENT = None
    OPENAI_AVAILABLE = False

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-2025-change-in-production")
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), "static"), exist_ok=True)
# Đảm bảo file font tồn tại cho PDF
if not os.path.exists(os.path.join("static", "Arial.ttf")):
    print("LƯU Ý QUAN TRỌNG: Để xuất PDF tiếng Việt hoạt động, bạn cần đặt file 'Arial.ttf' vào thư mục 'static'.")


ALLOWED_EXT = {"txt", "pdf", "docx", "csv", "xlsx"}
LOGO_PATH = "/static/Logo.png"

# ====================== GLOBAL DATA STORES ======================
CHI_BO = {}                      # "CB001": {"name": "...", "baso": "...", "bithu": "username", "hoatdong": [...]}
USER_CHIBO = {}                  # "dv01": "CB001", "bithu1": "CB001"
NHAN_XET = {}                    # dv_code -> text
DOCS = {}
CHAT_HISTORY = {}

# USERS (Tài khoản mẫu, mật khẩu đã được hash)
USERS = {
    "admin": {"password": generate_password_hash("Test@321"), "role": "admin", "name": "Quản trị viên"},
    "bithu1": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Bí thư Chi bộ 1"},
    "bithu2": {"password": generate_password_hash("Test@123"), "role": "bithu", "name": "Bí thư Chi bộ 2"},
    "user_demo": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "User Demo"},
    "dv01": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Đảng viên 01"},
    "dv02": {"password": generate_password_hash("Test@123"), "role": "dangvien", "name": "Đảng viên 02"},
}

# Dữ liệu mẫu khi khởi động
if not CHI_BO:
    CHI_BO["CB001"] = {
        "name": "Chi bộ 1",
        "baso": "12345",
        "bithu": "bithu1",
        "hoatdong": [f"[{datetime.now().strftime('%d/%m/%Y')}] Sinh hoạt định kỳ tháng 12"]
    }
    CHI_BO["CB002"] = {
        "name": "Chi bộ 2",
        "baso": "54321",
        "bithu": "bithu2",
        "hoatdong": [f"[{datetime.now().strftime('%d/%m/%Y')}] Hoạt động từ thiện"]
    }
    USER_CHIBO["bithu1"] = "CB001"
    USER_CHIBO["dv01"] = "CB001"
    USER_CHIBO["user_demo"] = "CB001"
    USER_CHIBO["bithu2"] = "CB002"
    USER_CHIBO["dv02"] = "CB002"
    
# Nhận xét mẫu
NHAN_XET["dv01"] = "Đảng viên tích cực, hoàn thành tốt nhiệm vụ được giao trong quý IV. Cần phát huy hơn nữa tinh thần xung kích."

FS_CLIENT = None
if FIRESTORE_AVAILABLE:
    try:
        FS_CLIENT = firestore.Client()
    except Exception:
        pass

# ====================== UTILITIES ======================
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

# ====================== PDF GENERATION UTILITY ======================
def generate_pdf_report(title, content_list, filename):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 72
    line_height = 16
    y = height - margin

    c.setFont(PDF_FONT_NAME, 16)
    c.drawCentredString(width / 2, y, title.upper())
    y -= 30

    c.setFont(PDF_FONT_NAME, 11)

    for item in content_list:
        if y < margin + line_height * 2:
            c.showPage()
            c.setFont(PDF_FONT_NAME, 11)
            y = height - margin - line_height

        if isinstance(item, tuple):
            # Format: (label, value)
            label, value = item
            c.drawString(margin, y, f"{label}:")
            
            # Sử dụng textobject cho wrap text
            textobject = c.beginText(margin + 120, y)
            textobject.setFont(PDF_FONT_NAME, 11)
            lines = c._get
            
            # Manual line wrapping (basic)
            lines = []
            current_line = ""
            words = value.split()
            
            for word in words:
                test_line = current_line + " " + word
                # Ước tính chiều rộng
                if c.stringWidth(test_line.strip(), PDF_FONT_NAME, 11) < width - 120 - margin:
                    current_line = test_line
                else:
                    lines.append(current_line.strip())
                    current_line = word
            lines.append(current_line.strip())

            for line in lines:
                c.drawString(margin + 120, y, line)
                y -= line_height
            y += line_height # Compensate for one extra line break before next item

        elif isinstance(item, str):
            # Simple line/header
            c.drawString(margin, y, item)
        
        y -= line_height * 1.5 # Space between items

    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

# ====================== AI & File Utilities (giữ nguyên) ======================
def read_file_text(path):
    # ... (function content remains the same)
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
    except Exception:
        pass
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:30000]
    except Exception:
        return ""
    return ""

def openai_summarize(text):
    # ... (function content remains the same)
    if not OPENAI_AVAILABLE or not text.strip():
        return "Không thể tóm tắt (thiếu OpenAI hoặc nội dung rỗng)."
    try:
        resp = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Tóm tắt tài liệu sau bằng tiếng Việt, 4-7 câu:\n\n{text[:6000]}"}],
            max_tokens=400,
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Lỗi tóm tắt bằng AI: {str(e)}"

def openai_answer(question, context=""):
    # ... (function content remains the same)
    if not OPENAI_AVAILABLE:
        return "AI chưa được cấu hình. (Thiếu OPENAI_API_KEY)"
    has_specific_context = ("NGỮ CẢNH TÀI LIỆU" in context or "NGỮ CẢNH TÌM KIẾM WEB" in context)
    if has_specific_context:
        messages = [
            {"role": "system", "content": "Bạn là trợ lý Đảng viên. Trả lời chính xác, trang trọng bằng tiếng Việt. CHỈ SỬ DỤNG thông tin được cung cấp trong NGỮ CẢNH TÀI LIỆU hoặc TÌM KIẾM WEB để trả lời, không giả định. **Nếu thông tin trong ngữ cảnh không đủ hoặc không liên quan đến câu hỏi, hãy trả lời bằng kiến thức nền của bạn, và thông báo rõ ràng rằng câu trả lời không đến từ tài liệu được cung cấp.**"},
            {"role": "user", "content": f"Ngữ cảnh:\n{context}\n\nCâu hỏi: {question}"}
        ]
    else:
        messages = [
            {"role": "system", "content": "Bạn là trợ lý Đảng viên. Trả lời chính xác, trang trọng bằng tiếng Việt."},
            {"role": "user", "content": question}
        ]
    try:
        resp = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=600,
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Lỗi khi gọi AI: {str(e)}"

# ====================== TEMPLATE (giữ nguyên) ======================
HEADER = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Hệ thống Quản lý Đảng viên</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        body {{ background: #f8fff8; padding-bottom: 100px; }}
        .navbar {{ background: #0f5132 !important; }}
        .footer {{ background: #0f5132; color: white; position: fixed; bottom: 0; width: 100%; padding: 12px 0; text-align: center; font-size: 0.9rem; }}
        #chat-button {{ position: fixed; right: 20px; bottom: 20px; z-index: 9999; width: 56px; height: 56px; border-radius: 50%; }}
        #chat-popup {{ position: fixed; right: 20px; bottom: 90px; width: 380px; max-width: 92vw; z-index: 9999; display: none; }}
        .chat-msg {{ margin-bottom: 5px; }}
    </style>
</head>
<body>
<nav class="navbar navbar-dark">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{{{ url_for('dashboard') }}}}">
      <img src="{LOGO_PATH}" alt="Logo" height="40" class="me-2">
      HỆ THỐNG QLNS - ĐẢNG VIÊN
    </a>
    {{% if session.user %}}
    <div class="text-white">
      <i class="bi bi-person-circle"></i> {{{{ session.user.name }}}} ({{{{ session.user.username }}}})
      <a href="{{{{ url_for('change_password') }}}}" class="btn btn-outline-light btn-sm ms-3">Đổi mật khẩu</a>
      <a href="{{{{ url_for('upload') }}}}" class="btn btn-outline-light btn-sm ms-3">Tải tài liệu</a>
      <a href="{{{{ url_for('logout') }}}}" class="btn btn-outline-light btn-sm ms-3">Đăng xuất</a>
    </div>
    {{% endif %}}
  </div>
</nav>
<div class="container mt-4">
"""

FOOTER = """
</div>
<div class="footer">
    © 2025 HỆ THỐNG QLNS - ĐẢNG VIÊN | Toàn bộ quyền được bảo lưu.
</div>
<button id="chat-button" class="btn btn-success shadow-lg fs-3">Chat</button>
<div id="chat-popup" class="card shadow-lg">
  <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
    <strong>Trợ lý AI</strong>
    <button id="clear-chat" class="btn btn-sm btn-outline-light me-2">Xóa lịch sử</button>
    <button id="close-chat" class="btn-close btn-close-white"></button>
  </div>
  <div class="card-body p-2">
    <div id="chat-messages" class="border bg-light mb-2" style="height:320px; overflow-y:auto; padding:8px;"></div>
    <form id="chat-form" class="d-flex">
      <input id="chat-input" class="form-control form-control-sm me-1" placeholder="Hỏi về Điều lệ, Nghị quyết...">
      <button id="chat-submit" class="btn btn-success btn-sm">Gửi</button>
    </form>
  </div>
</div>
<script>
const popup = document.getElementById('chat-popup');
const chatMessages = document.getElementById('chat-messages');
document.getElementById('chat-button').onclick = () => popup.style.display = 'block';
document.getElementById('close-chat').onclick = () => popup.style.display = 'none';
document.getElementById('clear-chat').onclick = async () => {
    if (confirm("Bạn có chắc chắn muốn xóa lịch sử trò chuyện?")) {
        try {
            await fetch('/api/chat/clear', {method:'POST'});
            chatMessages.innerHTML = '';
            addMsg('Lịch sử trò chuyện đã được xóa.', 'system', true);
        } catch(e) {
            alert('Lỗi khi xóa lịch sử.');
        }
    }
};
async function sendQuestion(q) {
  if (!q.trim()) return;
  document.getElementById('chat-input').value = '';
  addMsg(q, 'user');
  addMsg('Đang suy nghĩ...', 'bot');
  try {
    const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:q})});
    const j = await r.json();
    removeLastBot();
    const answerText = (j.answer || j.error || 'Lỗi: Không thể lấy câu trả lời từ server.').replace(/\\n/g, '<br>');
    addMsg(answerText, 'bot');
  } catch(e) { removeLastBot(); addMsg('Lỗi kết nối hoặc server.', 'bot'); }
}
function addMsg(text, sender, isSystem=false) {
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (sender==='user'?'text-end':'');
  let senderName = sender === 'user' ? 'Bạn' : 'AI';
  let className = isSystem ? 'bg-warning text-dark' : (sender==='user'?'bg-primary text-white':'bg-light');
  div.innerHTML = `<small class="text-muted">${senderName}</small><div class="p-2 rounded ${className} d-inline-block">${text}</div>`;
  chatMessages.appendChild(div);
  div.scrollIntoView();
}
function removeLastBot() {
  const bots = chatMessages.querySelectorAll('.chat-msg:not(.text-end)');
  if (bots.length) bots[bots.length-1].remove();
}
document.getElementById('chat-form').onsubmit = e => { e.preventDefault(); sendQuestion(document.getElementById('chat-input').value); };
</script>
</body>
</html>
"""

# ====================== ROUTES ======================
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = USERS.get(username)
        if user and check_password_hash(user["password"], password):
            session["user"] = {
                "username": username,
                "role": user["role"],
                "name": user.get("name", username),
                "chibo": USER_CHIBO.get(username)
            }
            return redirect(url_for("dashboard"))
        flash("Sai tài khoản hoặc mật khẩu", "danger")
    return render_template_string(HEADER + """
    <div class="row justify-content-center">
      <div class="col-md-4">
        <div class="card shadow">
          <div class="card-body">
            <h4 class="text-center mb-4">Đăng nhập hệ thống</h4>
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
            {% endwith %}
            <form method="post">
              <div class="mb-3"><input class="form-control" name="username" placeholder="Tài khoản" required autofocus></div>
              <div class="mb-3"><input class="form-control" type="password" name="password" placeholder="Mật khẩu" required></div>
              <button class="btn btn-success w-100">Đăng nhập</button>
            </form>
            <div class="alert alert-info mt-3 small">
              <strong>Demo:</strong> Tài khoản Admin (admin) | Bí thư (bithu1) | Đảng viên (dv01)
            </div>
          </div>
        </div>
      </div>
    </div>
    """ + FOOTER)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["user"]["role"]
    if role == "admin": return redirect(url_for("admin_panel"))
    if role == "bithu": return redirect(url_for("chi_bo_panel"))
    return redirect(url_for("dangvien_panel"))

# ====================== ADMIN PANEL - QUẢN LÝ TỔNG HỢP ======================
@app.route("/admin")
@admin_required
def admin_panel():
    # Đếm số đảng viên mỗi chi bộ
    count_dv = {}
    for code in CHI_BO:
        count_dv[code] = sum(1 for u,c in USER_CHIBO.items() if c==code and USERS[u]["role"]=="dangvien")
    
    return render_template_string(HEADER + """
    <h3 class="text-success">Quản trị viên</h3>
    
    <div class="d-flex mb-3">
        <a href="{{url_for('admin_user_list')}}" class="btn btn-info me-2">Quản lý Users/Đảng viên</a>
        <a href="{{url_for('admin_add_chibo')}}" class="btn btn-success">Thêm Chi bộ mới</a>
    </div>

    <h4 class="mt-4">Danh sách Chi bộ</h4>
    <table class="table table-bordered table-hover">
      <thead class="table-success">
        <tr><th>Mã chi bộ</th><th>Tên chi bộ</th><th>Bí thư</th><th>Số đảng viên</th><th>Hành động</th></tr>
      </thead>
      <tbody>
      {% for code,info in chibo.items() %}
        <tr>
          <td><strong>{{code}}</strong></td>
          <td>{{info.name}}</td>
          <td>{{users.get(info.bithu, {'name':'(trống)'}).name}}</td>
          <td>{{count.get(code,0)}}</td>
          <td>
            <a href="{{url_for('admin_chibo_detail', code=code)}}" class="btn btn-sm btn-primary">Quản lý</a>
          </td>
        </tr>
      {% else %}
        <tr><td colspan="5" class="text-center text-muted">Chưa có chi bộ nào</td></tr>
      {% endfor %}
      </tbody>
    </table>
    """ + FOOTER, chibo=CHI_BO, users=USERS, count=count_dv)

# --- Admin: Quản lý Users (giữ nguyên logic) ---
@app.route("/admin/users")
@admin_required
def admin_user_list():
    all_users = sorted(USERS.keys())
    return render_template_string(HEADER + """
    <h4>Quản lý Users và Đảng viên</h4>
    <a href="{{url_for('admin_add_user')}}" class="btn btn-success mb-3">Thêm User mới</a>
    <table class="table table-bordered table-hover">
        <thead class="table-info">
            <tr><th>Tài khoản</th><th>Họ tên</th><th>Vai trò</th><th>Chi bộ</th><th>Hành động</th></tr>
        </thead>
        <tbody>
        {% for u in all_users %}
            {% set info = users[u] %}
            <tr>
                <td><strong>{{u}}</strong></td>
                <td>{{info.name}}</td>
                <td>{{info.role.upper()}}</td>
                <td>{{chibo_map.get(u, 'Chưa gán')}}</td>
                <td>
                    <a href="{{url_for('admin_edit_user', username=u)}}" class="btn btn-sm btn-warning">Sửa</a>
                </td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    """ + FOOTER, users=USERS, chibo_map=USER_CHIBO)

@app.route("/admin/users/add", methods=["GET","POST"])
@admin_required
def admin_add_user():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        name = request.form["name"].strip()
        password = request.form["password"]
        role = request.form["role"]
        chibo_code = request.form.get("chibo_code")

        if username in USERS:
            flash("Tài khoản đã tồn tại!", "danger")
        elif not re.match(r'^[a-z0-9_]{3,}$', username):
            flash("Tên đăng nhập không hợp lệ (chỉ được dùng chữ thường, số, _, tối thiểu 3 ký tự)", "danger")
        elif len(password) < 6:
            flash("Mật khẩu phải có ít nhất 6 ký tự", "danger")
        else:
            USERS[username] = {
                "password": generate_password_hash(password),
                "role": role,
                "name": name
            }
            if chibo_code and chibo_code in CHI_BO:
                if role == "bithu" and CHI_BO[chibo_code].get("bithu") and CHI_BO[chibo_code]["bithu"] != username:
                    flash(f"Lưu user thành công. Lưu ý: Chi bộ {chibo_code} đã có Bí thư, không gán vai trò Bí thư.", "warning")
                else:
                    USER_CHIBO[username] = chibo_code
                    flash("Thêm User và gán chi bộ thành công!", "success")
            else:
                flash("Thêm User thành công!", "success")
            
            return redirect(url_for("admin_user_list"))

    roles = ["dangvien", "bithu", "admin"]
    return render_template_string(HEADER + """
    <h4>Thêm User mới</h4>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
    {% endwith %}
    <form method="post" class="col-md-6">
      <div class="mb-3"><input name="username" class="form-control" placeholder="Tên đăng nhập (username)" required></div>
      <div class="mb-3"><input name="name" class="form-control" placeholder="Họ và tên" required></div>
      <div class="mb-3"><input type="password" name="password" class="form-control" placeholder="Mật khẩu (ít nhất 6 ký tự)" required></div>
      <div class="mb-3">
        <label class="form-label">Vai trò</label>
        <select name="role" class="form-select" required>
          {% for r in roles %}
            <option value="{{r}}">{{r.upper()}}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label">Gán vào Chi bộ (Không bắt buộc)</label>
        <select name="chibo_code" class="form-select">
          <option value="">-- Không gán Chi bộ --</option>
          {% for code, info in chibo.items() %}
            <option value="{{code}}">{{info.name}} ({{code}})</option>
          {% endfor %}
        </select>
      </div>
      <button class="btn btn-success">Tạo User</button>
      <a href="{{url_for('admin_user_list')}}" class="btn btn-secondary">Hủy</a>
    </form>
    """ + FOOTER, roles=roles, chibo=CHI_BO)

@app.route("/admin/users/edit/<username>", methods=["GET","POST"])
@admin_required
def admin_edit_user(username):
    if username not in USERS: abort(404)
    user_data = USERS[username]
    current_chibo = USER_CHIBO.get(username)
    
    if request.method == "POST":
        name = request.form["name"].strip()
        role = request.form["role"]
        new_password = request.form.get("new_password")
        chibo_code = request.form.get("chibo_code")
        
        # 1. Cập nhật thông tin cơ bản
        user_data["name"] = name
        user_data["role"] = role
        if new_password:
            if len(new_password) < 6:
                flash("Mật khẩu mới phải có ít nhất 6 ký tự. KHÔNG CẬP NHẬT mật khẩu.", "danger")
            else:
                user_data["password"] = generate_password_hash(new_password)
                flash("Đã đổi mật khẩu", "success")

        # 2. Cập nhật Chi bộ
        # Xóa khỏi chi bộ cũ
        if username in USER_CHIBO:
            if CHI_BO.get(USER_CHIBO[username]) and CHI_BO[USER_CHIBO[username]].get("bithu") == username:
                # Nếu là Bí thư bị gỡ khỏi chi bộ, phải xóa vai trò Bí thư của Chi bộ đó
                CHI_BO[USER_CHIBO[username]]["bithu"] = ""
            del USER_CHIBO[username]
        
        # Gán vào chi bộ mới
        if chibo_code and chibo_code in CHI_BO:
            # Nếu user được đặt làm Bí thư cho chi bộ này, cần cập nhật chi bộ
            if role == "bithu":
                if CHI_BO[chibo_code].get("bithu"):
                    # Nếu chi bộ đã có Bí thư khác, không cho gán
                    flash(f"User được gán vai trò Bí thư nhưng Chi bộ {chibo_code} đã có Bí thư khác. KHÔNG GÁN CHI BỘ.", "warning")
                else:
                    CHI_BO[chibo_code]["bithu"] = username
                    USER_CHIBO[username] = chibo_code
            else:
                 USER_CHIBO[username] = chibo_code
        
        flash("Cập nhật thông tin User thành công!", "success")
        return redirect(url_for("admin_user_list"))

    roles = ["dangvien", "bithu", "admin"]
    return render_template_string(HEADER + """
    <h4>Chỉnh sửa User: {{username}}</h4>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
    {% endwith %}
    <form method="post" class="col-md-6">
      <div class="mb-3"><label class="form-label">Tên đăng nhập (Không sửa)</label>
        <input class="form-control" value="{{username}}" disabled></div>
      <div class="mb-3"><label class="form-label">Họ và tên</label>
        <input name="name" class="form-control" value="{{user_data.name}}" required></div>
      <div class="mb-3"><label class="form-label">Mật khẩu mới (Để trống nếu không đổi)</label>
        <input type="password" name="new_password" class="form-control" placeholder="Mật khẩu mới (ít nhất 6 ký tự)"></div>
      <div class="mb-3">
        <label class="form-label">Vai trò</label>
        <select name="role" class="form-select" required>
          {% for r in roles %}
            <option value="{{r}}" {% if r == user_data.role %}selected{% endif %}>{{r.upper()}}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label">Gán vào Chi bộ</label>
        <select name="chibo_code" class="form-select">
          <option value="">-- Không gán Chi bộ --</option>
          {% for code, info in chibo.items() %}
            <option value="{{code}}" {% if code == current_chibo %}selected{% endif %}>{{info.name}} ({{code}})</option>
          {% endfor %}
        </select>
      </div>
      <button class="btn btn-warning">Cập nhật User</button>
      <a href="{{url_for('admin_user_list')}}" class="btn btn-secondary">Hủy</a>
    </form>
    """ + FOOTER, user_data=user_data, username=username, roles=roles, chibo=CHI_BO, current_chibo=current_chibo)

# --- Admin: Quản lý Chi bộ (Đã sửa lỗi thêm Chi bộ) ---
@app.route("/admin/chibo/add", methods=["GET","POST"])
@admin_required
def admin_add_chibo():
    if request.method == "POST":
        code = request.form["code"].strip().upper()
        name = request.form["name"].strip()
        bithu = request.form["bithu"]
        if code in CHI_BO:
            flash("Mã chi bộ đã tồn tại!", "danger")
        elif not name or not bithu:
            flash("Vui lòng nhập đầy đủ", "danger")
        elif bithu not in USERS or USERS[bithu]["role"] != "bithu":
            flash("Bí thư không tồn tại hoặc không đúng vai trò", "danger")
        elif USER_CHIBO.get(bithu):
            flash("Bí thư này đã thuộc chi bộ khác", "danger")
        else:
            # FIX: Logic thêm Chi bộ và gán Bí thư
            CHI_BO[code] = {"name": name, "baso": "", "bithu": bithu, "hoatdong": []}
            USER_CHIBO[bithu] = code
            flash("Tạo chi bộ thành công!", "success")
            return redirect(url_for("admin_panel"))
    
    # Lấy danh sách Bí thư chưa được gán cho Chi bộ nào
    free_bithu = [u for u,i in USERS.items() if i["role"]=="bithu" and u not in USER_CHIBO]
    return render_template_string(HEADER + """
    <h4>Thêm Chi bộ mới</h4>
    <form method="post" class="col-md-6">
      <div class="mb-3"><input name="code" class="form-control" placeholder="Mã chi bộ (vd: CB001)" required></div>
      <div class="mb-3"><input name="name" class="form-control" placeholder="Tên chi bộ" required></div>
      <div class="mb-3">
        <label class="form-label">Chọn Bí thư</label>
        <select name="bithu" class="form-select" required>
          <option value="">-- Chọn Bí thư --</option>
          {% for u in free_bithu %}
            <option value="{{u}}">{{users[u].name}} ({{u}})</option>
          {% endfor %}
        </select>
        {% if not free_bithu %}
          <div class="form-text text-danger">Không có Bí thư nào chưa được gán. Hãy tạo thêm Bí thư mới ở mục Quản lý Users.</div>
        {% endif %}
      </div>
      <button class="btn btn-success">Tạo Chi bộ</button>
      <a href="{{url_for('admin_panel')}}" class="btn btn-secondary">Hủy</a>
    </form>
    """ + FOOTER, free_bithu=free_bithu, users=USERS)

@app.route("/admin/chibo/<code>")
@admin_required
def admin_chibo_detail(code):
    if code not in CHI_BO: abort(404)
    info = CHI_BO[code]
    members = [u for u,c in USER_CHIBO.items() if c == code]
    return render_template_string(HEADER + """
    <h4>Chi bộ: {{info.name}} ({{code}})</h4>
    <p><strong>Bí thư:</strong> {{users.get(info.bithu, {'name':'(trống)'}).name}}</p>
    <div class="d-flex mb-3">
        <a href="{{url_for('admin_add_member', code=code)}}" class="btn btn-success me-2">Thêm đảng viên</a>
        <a href="{{url_for('export_chibo_report', code=code)}}" class="btn btn-primary" target="_blank">Xuất Báo cáo Chi bộ (PDF)</a>
    </div>
    
    <table class="table table-sm table-bordered">
      <tr><th>Tài khoản</th><th>Họ tên</th><th>Vai trò</th><th>Hành động</th><th>Báo cáo cá nhân</th></tr>
      {% for u in members %}
      <tr>
        <td>{{u}}</td>
        <td>{{users[u].name}}</td>
        <td>{{"Bí thư" if u==info.bithu else "Đảng viên"}}</td>
        <td>
          {% if u != info.bithu %}
            <a href="{{url_for('admin_remove_member', code=code, username=u)}}" class="btn btn-sm btn-danger"
               onclick="return confirm('Xóa khỏi chi bộ?')">Xóa</a>
          {% endif %}
        </td>
        <td>
            {% if u != info.bithu %}
                <a href="{{url_for('export_dv_report', dv=u)}}" class="btn btn-sm btn-info" target="_blank">Xuất Nhận xét (PDF)</a>
            {% else %}
                -
            {% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
    <h5 class="mt-4">Hoạt động Chi bộ gần đây</h5>
    <ul>
      {% for hd in info.hoatdong | reverse %}
        <li>{{hd}}</li>
      {% endfor %}
    </ul>
    <a href="{{url_for('admin_panel')}}" class="btn btn-secondary">Quay lại</a>
    """ + FOOTER, info=info, members=members, users=USERS, code=code)

@app.route("/admin/chibo/<code>/add", methods=["GET","POST"])
@admin_required
def admin_add_member(code):
    # ... (content remains the same)
    if code not in CHI_BO: abort(404)
    if request.method == "POST":
        username = request.form["username"]
        if username not in USERS:
            flash("User không tồn tại", "danger")
        elif USER_CHIBO.get(username):
            flash("User đã thuộc chi bộ khác", "danger")
        else:
            USER_CHIBO[username] = code
            flash("Thêm thành công", "success")
            return redirect(url_for("admin_chibo_detail", code=code))
    available = [u for u,i in USERS.items() if i["role"] in ["dangvien","bithu"] and u not in USER_CHIBO]
    return render_template_string(HEADER + """
    <h5>Thêm thành viên vào {{chibo[code].name}}</h5>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
    {% endwith %}
    <form method="post">
      <select name="username" class="form-select mb-3" required>
        <option value="">-- Chọn User --</option>
        {% for u in available %}
          <option value="{{u}}">{{users[u].name}} ({{u}} - {{users[u].role.upper()}})</option>
        {% endfor %}
      </select>
      {% if not available %}
        <div class="form-text text-danger mb-3">Không có User nào chưa được gán.</div>
      {% endif %}
      <button class="btn btn-success" {% if not available %}disabled{% endif %}>Thêm</button>
      <a href="{{url_for('admin_chibo_detail', code=code)}}" class="btn btn-secondary">Hủy</a>
    </form>
    """ + FOOTER, available=available, users=USERS, chibo=CHI_BO, code=code)

@app.route("/admin/chibo/<code>/remove/<username>")
@admin_required
def admin_remove_member(code, username):
    if USER_CHIBO.get(username) == code:
        if CHI_BO.get(code) and CHI_BO[code].get("bithu") == username:
             # Nếu là Bí thư bị gỡ khỏi chi bộ, phải xóa vai trò Bí thư của Chi bộ đó
             CHI_BO[code]["bithu"] = ""
        del USER_CHIBO[username]
        flash("Đã xóa khỏi chi bộ", "success")
    return redirect(url_for("admin_chibo_detail", code=code))

# ====================== BÍ THƯ CHI BỘ PANEL ======================
@app.route("/chi-bo")
@login_required("bithu")
def chi_bo_panel():
    username = session["user"]["username"]
    chibo_code = USER_CHIBO.get(username)
    if not chibo_code or chibo_code not in CHI_BO:
        flash("Bạn chưa được gán chi bộ!", "danger"); return redirect(url_for("logout"))
    info = CHI_BO[chibo_code]
    dangvien_list = [u for u,c in USER_CHIBO.items() if c == chibo_code and USERS[u]["role"] == "dangvien"]
    
    return render_template_string(HEADER + """
    <h3 class="text-success">Bí thư Chi bộ: {{info.name}}</h3>
    <a href="{{url_for('export_chibo_report', code=chibo_code)}}" class="btn btn-primary mb-3" target="_blank">Xuất Báo cáo Chi bộ (PDF)</a>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
    {% endwith %}

    <form method="post" action="{{url_for('chi_bo_update', code=chibo_code)}}">
      <div class="mb-3"><label class="form-label">Mã số Chi bộ (baso)</label>
        <input name="baso" class="form-control" value="{{info.get('baso','')}}"></div>
      <div class="mb-3"><label class="form-label">Thêm hoạt động</label>
        <textarea name="hoatdong" class="form-control" rows="3" placeholder="Nội dung hoạt động mới..."></textarea></div>
      <button class="btn btn-success">Lưu / Thêm</button>
    </form>
    
    <h5 class="mt-4">Hoạt động chi bộ</h5><ol>
      {% for a in info.hoatdong | reverse %}<li>{{a}}</li>{% else %}<li class="text-muted">Chưa có</li>{% endfor %}
    </ol>
    
    <h5>Nhận xét Đảng viên</h5>
    <div class="list-group">
      {% for u in dangvien_list %}
        <a href="{{url_for('nhanxet_edit', dv=u)}}" class="list-group-item list-group-item-action">
            {{users[u].name}} ({{u}}) 
            <a href="{{url_for('export_dv_report', dv=u)}}" class="btn btn-sm btn-info float-end ms-2" target="_blank">Xuất Nhận xét (PDF)</a>
        </a>
      {% else %}<p class="text-muted">Chưa có đảng viên</p>{% endfor %}
    </div>
    """ + FOOTER, info=info, users=USERS, dangvien_list=dangvien_list, chibo_code=chibo_code)

@app.route("/chi-bo/update/<code>", methods=["POST"])
@login_required("bithu")
def chi_bo_update(code):
    if code != USER_CHIBO.get(session["user"]["username"]): abort(403)
    baso = request.form.get("baso","").strip()
    hd = request.form.get("hoatdong","").strip()
    if baso: CHI_BO[code]["baso"] = baso
    if hd: CHI_BO[code]["hoatdong"].append(f"[{datetime.now().strftime('%d/%m/%Y')}] {hd}")
    return redirect(url_for("chi_bo_panel"))

# ====================== ĐẢNG VIÊN PANEL (giữ nguyên) ======================
@app.route("/dangvien")
@login_required("dangvien")
def dangvien_panel():
    username = session["user"]["username"]
    chibo_code = USER_CHIBO.get(username)
    if not chibo_code or chibo_code not in CHI_BO:
        return render_template_string(HEADER + "<h3 class='text-danger'>Bạn chưa thuộc chi bộ nào.</h3>" + FOOTER)
    info = CHI_BO[chibo_code]
    nhanxet = NHAN_XET.get(username, "Chưa có nhận xét từ Bí thư.")
    return render_template_string(HEADER + """
    <h3>Xin chào <strong>{{session.user.name}}</strong></h3>
    <div class="card mb-3">
      <div class="card-header bg-success text-white">Thông tin chi bộ</div>
      <div class="card-body">
        <p><strong>Tên chi bộ:</strong> {{info.name}}</p>
        <p><strong>Bí thư:</strong> {{users.get(info.bithu, {'name':'(trống)'}).name}}</p>
        <p><strong>Mã số:</strong> {{info.get('baso') or 'Chưa thiết lập'}}</p>
      </div>
    </div>
    <div class="card mb-3">
      <div class="card-header bg-success text-white">Nhận xét của Bí thư</div>
      <div class="card-body">
        {{nhanxet}}
        <a href="{{url_for('export_dv_report', dv=username)}}" class="btn btn-sm btn-outline-success float-end mt-2" target="_blank">Xuất Nhận xét (PDF)</a>
      </div>
    </div>
    <div class="card">
      <div class="card-header bg-success text-white">Hoạt động chi bộ</div>
      <div class="card-body"><ol>
        {% for a in info.hoatdong | reverse %}<li>{{a}}</li>{% else %}<li>Chưa có hoạt động</li>{% endfor %}
      </ol></div>
    </div>
    """ + FOOTER, info=info, nhanxet=nhanxet, users=USERS, username=username)

# ====================== NHẬN XÉT ======================
@app.route("/nhanxet/<dv>", methods=["GET","POST"])
@login_required("bithu")
def nhanxet_edit(dv):
    if dv not in USERS or USERS[dv]["role"] != "dangvien":
        abort(404)
    bithu_chibo = USER_CHIBO.get(session["user"]["username"])
    dv_chibo = USER_CHIBO.get(dv)
    
    if bithu_chibo != dv_chibo: 
        flash("Bạn không có quyền nhận xét Đảng viên này (không cùng Chi bộ)", "danger")
        return redirect(url_for("chi_bo_panel"))
        
    if request.method == "POST":
        NHAN_XET[dv] = request.form["noidung"]
        flash("Đã lưu nhận xét", "success")
    
    return render_template_string(HEADER + """
    <h4>Nhận xét Đảng viên: {{users[dv].name}}</h4>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
    {% endwith %}
    <form method="post">
      <textarea name="noidung" class="form-control" rows="10">{{NHAN_XET.get(dv,'')}}</textarea>
      <button class="btn btn-success mt-3">Lưu</button>
      <a href="{{url_for('chi_bo_panel')}}" class="btn btn-secondary ms-2 mt-3">Quay lại</a>
    </form>
    """ + FOOTER, users=USERS, dv=dv, NHAN_XET=NHAN_XET)

# ====================== EXPORT PDF ROUTES ======================

@app.route("/export/dv/<dv>")
@login_required()
def export_dv_report(dv):
    if dv not in USERS or USERS[dv]["role"] != "dangvien":
        abort(404)
        
    user = session["user"]
    dv_chibo = USER_CHIBO.get(dv)
    
    # Kiểm tra quyền: Admin, hoặc Bí thư/Đảng viên cùng Chi bộ, hoặc chính bản thân Đảng viên đó
    has_permission = (user["role"] == "admin" or 
                      user["username"] == dv or 
                      USER_CHIBO.get(user["username"]) == dv_chibo)
    
    if not has_permission:
        abort(403)

    dv_info = USERS[dv]
    chibo_name = CHI_BO.get(dv_chibo, {}).get("name", "N/A")
    nhanxet_text = NHAN_XET.get(dv, "Chưa có nhận xét.")
    
    title = f"Báo cáo nhận xét Đảng viên {dv_info['name']}"
    content = [
        ("Họ tên", dv_info['name']),
        ("Tài khoản", dv),
        ("Vai trò", "Đảng viên"),
        ("Chi bộ", chibo_name),
        "",
        "--- NỘI DUNG NHẬN XÉT CỦA BÍ THƯ ---",
        ("", nhanxet_text)
    ]
    
    return generate_pdf_report(title, content, f"NhanXet_{dv}_{datetime.now().strftime('%Y%m%d')}.pdf")

@app.route("/export/chibo/<code>")
@login_required()
def export_chibo_report(code):
    if code not in CHI_BO: abort(404)
    
    user = session["user"]
    chibo_info = CHI_BO[code]
    
    # Kiểm tra quyền: Admin, hoặc Bí thư Chi bộ đó
    has_permission = (user["role"] == "admin" or 
                      chibo_info.get("bithu") == user["username"])
    
    if not has_permission:
        abort(403)
        
    members = [u for u,c in USER_CHIBO.items() if c == code]
    dangvien_list = [u for u in members if USERS[u]["role"] == "dangvien"]
    
    title = f"Báo cáo Chi bộ {chibo_info['name']} ({code})"
    content = [
        ("Tên Chi bộ", chibo_info['name']),
        ("Mã số (baso)", chibo_info.get('baso', 'N/A')),
        ("Bí thư", USERS.get(chibo_info.get('bithu'), {}).get('name', 'N/A')),
        ("Số Đảng viên", str(len(dangvien_list))),
        "",
        "--- HOẠT ĐỘNG CHI BỘ GẦN ĐÂY ---",
    ]
    
    for hd in chibo_info.get('hoatdong', [])[::-1]:
        content.append(hd)
        
    content.append("")
    content.append("--- NHẬN XÉT VỀ CÁC ĐẢNG VIÊN ---")
    
    for dv in dangvien_list:
        nhanxet_dv = NHAN_XET.get(dv, "Chưa có nhận xét.")
        content.append(f"**Đảng viên: {USERS[dv]['name']} ({dv})**")
        content.append(("", nhanxet_dv))

    return generate_pdf_report(title, content, f"BaoCaoChiBo_{code}_{datetime.now().strftime('%Y%m%d')}.pdf")

# ====================== CÁC ROUTE KHÁC (giữ nguyên) ======================
# ... (Các route /upload, /doc/<fn>, /change-password, /api/chat giữ nguyên)
@app.route("/upload", methods=["GET","POST"])
@login_required()
def upload():
    # ... (content remains the same)
    if request.method == "POST":
        if "file" not in request.files:
            flash("Không tìm thấy file tải lên", "danger")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("Chưa chọn file", "danger")
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            
            text = read_file_text(filepath)
            summary = openai_summarize(text)
            
            DOCS[filename] = {
                "user": session["user"]["username"],
                "role": session["user"]["role"],
                "path": filepath,
                "summary": summary,
                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            flash(f"Đã tải lên file: {filename}. Đang tạo tóm tắt...", "success")
            return redirect(url_for("doc_view", fn=filename))
        else:
            flash("Loại file không được hỗ trợ", "danger")
    
    # Lọc tài liệu theo chi bộ/admin
    if session["user"]["role"] == "admin":
        user_docs = DOCS
    else:
        user_docs = {
            fn: info for fn, info in DOCS.items() 
            if info["user"] == session["user"]["username"] or 
               (USER_CHIBO.get(session["user"]["username"]) == USER_CHIBO.get(info["user"]) and info["role"] != "admin")
        }
    
    return render_template_string(HEADER + """
    <h3>Tải lên Tài liệu mới</h3>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
    {% endwith %}
    <form method="post" enctype="multipart/form-data" class="mb-5">
      <input type="file" name="file" class="form-control mb-3" required>
      <button type="submit" class="btn btn-success">Tải lên</button>
    </form>
    
    <hr>
    
    <h5 class="mt-4">Các Tài liệu đã tải lên</h5>
    <table class="table table-bordered table-sm">
      <thead class="table-info">
        <tr><th>Tên file</th><th>Người tải</th><th>Tóm tắt</th><th>Xem</th></tr>
      </thead>
      <tbody>
        {% for fn, info in user_docs.items() %}
          <tr>
            <td>{{fn}}</td>
            <td>{{users.get(info.user, {'name': 'N/A'}).name}}</td>
            <td>{{info.summary[:50]}}...</td>
            <td><a href="{{url_for('doc_view', fn=fn)}}" class="btn btn-sm btn-info">Xem chi tiết</a></td>
          </tr>
        {% else %}
          <tr><td colspan="4" class="text-center text-muted">Chưa có tài liệu nào được tải lên.</td></tr>
        {% endfor %}
      </tbody>
    </table>
    """ + FOOTER, users=USERS, user_docs=user_docs)


@app.route("/doc/<fn>")
@login_required()
def doc_view(fn):
    # ... (content remains the same)
    if fn not in DOCS: abort(404)
    info = DOCS[fn]
    
    # Kiểm tra quyền truy cập (Admin xem tất cả, User xem file của mình hoặc file chung chi bộ)
    user = session["user"]
    if user["role"] != "admin":
        if info["user"] != user["username"]:
            if USER_CHIBO.get(user["username"]) != USER_CHIBO.get(info["user"]):
                abort(403)
                
    content = ""
    try:
        # Đọc nội dung file, giới hạn hiển thị
        full_content = read_file_text(info["path"])
        content_display = full_content[:5000].replace('\n', '<br>')
        if len(full_content) > 5000:
             content_display += "...<br><br>... (Chỉ hiển thị 5000 ký tự đầu tiên)"
        content = content_display
    except Exception as e:
        content = f"Lỗi đọc file: {str(e)}"
        
    return render_template_string(HEADER + """
    <h4>Tài liệu: {{fn}}</h4>
    <p><strong>Người tải:</strong> {{users.get(info.user, {'name': 'N/A'}).name}} | <strong>Thời gian:</strong> {{info.uploaded_at}}</p>
    <div class="card mb-3">
      <div class="card-header bg-primary text-white">Tóm tắt AI</div>
      <div class="card-body">{{info.summary.replace('\n', '<br>') | safe}}</div>
    </div>
    <div class="card">
      <div class="card-header bg-secondary text-white">Nội dung (Trích đoạn)</div>
      <div class="card-body small" style="white-space: pre-wrap;">{{content | safe}}</div>
    </div>
    <a href="{{url_for('upload')}}" class="btn btn-secondary mt-3">Quay lại</a>
    """ + FOOTER, fn=fn, info=info, users=USERS, content=content)


@app.route("/change-password", methods=["GET","POST"])
@login_required()
def change_password():
    # ... (content remains the same)
    username = session["user"]["username"]
    if request.method == "POST":
        old_pass = request.form["old_password"]
        new_pass = request.form["new_password"]
        
        if not check_password_hash(USERS[username]["password"], old_pass):
            flash("Mật khẩu cũ không đúng", "danger")
        elif len(new_pass) < 6:
            flash("Mật khẩu mới phải có ít nhất 6 ký tự", "danger")
        else:
            USERS[username]["password"] = generate_password_hash(new_pass)
            flash("Đổi mật khẩu thành công!", "success")
            return redirect(url_for("dashboard"))
            
    return render_template_string(HEADER + """
    <div class="row justify-content-center">
      <div class="col-md-5">
        <h4>Đổi mật khẩu cho {{session.user.name}}</h4>
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}<div class="alert alert-{{messages[0][0]}}">{{messages[0][1]}}</div>{% endif %}
        {% endwith %}
        <form method="post" class="card card-body">
          <div class="mb-3"><input class="form-control" type="password" name="old_password" placeholder="Mật khẩu cũ" required></div>
          <div class="mb-3"><input class="form-control" type="password" name="new_password" placeholder="Mật khẩu mới" required></div>
          <button class="btn btn-success">Đổi mật khẩu</button>
        </form>
      </div>
    </div>
    """ + FOOTER)

@app.route("/api/chat", methods=["POST"])
@login_required()
def chat_api():
    # ... (content remains the same)
    username = session["user"]["username"]
    question = request.json.get("question", "").strip()
    
    if not question:
        return jsonify({"error": "Câu hỏi không được rỗng"}), 400
        
    if username not in CHAT_HISTORY:
        CHAT_HISTORY[username] = []
        
    # Xử lý ngữ cảnh tài liệu
    doc_context = ""
    relevant_docs = {
        fn: info for fn, info in DOCS.items() 
        if info["user"] == username or 
           session["user"]["role"] == "admin" or
           (USER_CHIBO.get(username) == USER_CHIBO.get(info["user"]) and info["role"] != "admin")
    }
    
    if relevant_docs:
        doc_context = "NGỮ CẢNH TÀI LIỆU:\n"
        for fn, info in relevant_docs.items():
            doc_context += f"***Tài liệu: {fn} (Tóm tắt)***\n{info['summary']}\n\n"
        doc_context = doc_context[:4000] # Giới hạn kích thước ngữ cảnh
        
    # Xử lý ngữ cảnh chi bộ
    chibo_code = USER_CHIBO.get(username, '')
    chibo_info = CHI_BO.get(chibo_code, {})
    chibo_context = f"NGỮ CẢNH CHI BỘ:\nTên chi bộ: {chibo_info.get('name','N/A')}\nMã số: {chibo_info.get('baso','Chưa thiết lập')}\nHoạt động gần nhất: {chibo_info.get('hoatdong', ['N/A'])[-1] if chibo_info.get('hoatdong') else 'N/A'}\n"
    
    context = chibo_context + doc_context
    
    answer = openai_answer(question, context=context)
    
    CHAT_HISTORY[username].append({"user": question, "ai": answer})
    
    return jsonify({"answer": answer})

@app.route("/api/chat/clear", methods=["POST"])
@login_required()
def chat_clear_api():
    # ... (content remains the same)
    username = session["user"]["username"]
    if username in CHAT_HISTORY:
        del CHAT_HISTORY[username]
    return jsonify({"status": "success"})

@app.route("/static/<path:p>")
def serve_static(p):
    return send_from_directory("static", p)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
