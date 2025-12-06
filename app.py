import os
import re
from flask import Flask, request, redirect, url_for, render_template_string, session, abort, flash
from werkzeug.utils import secure_filename
from openai import OpenAI
from tavily import TavilyClient

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecret")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXT = {"txt", "pdf", "docx"}

# OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Tavily
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# -------------------------------------------------------
# DATA LƯU TẠM (Render FREE không chạy DB lớn)
# -------------------------------------------------------
USERS = {
    "admin": {"password": "123", "role": "admin"},
    "bithu": {"password": "123", "role": "bithu"},
    "dv01": {"password": "123", "role": "dangvien"},
}

NHAN_XET = {}     # theo mã đảng viên
SINH_HOAT = []    # hoạt động chung chi bộ
DOCS = {}         # tài liệu upload
CHAT_HISTORY = {} # lịch sử hỏi AI

# -------------------------------------------------------
# TEMPLATE BASE
# -------------------------------------------------------
def base_template(content):
    return f"""
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Chi Bộ Đảng</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>body {{ padding:20px; }}</style>
</head>
<body>

<nav class="navbar navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <span class="navbar-brand">Hệ Thống Chi Bộ</span>
    <span class="navbar-text text-white">
      {session.get('user', {}).get('username', '')}
      {% if session.get('user') %}
      <a href="/logout" class="btn btn-danger btn-sm ms-3">Đăng xuất</a>
      {% endif %}
    </span>
  </div>
</nav>

<div class="container">{content}</div>

</body>
</html>
"""

# -------------------------------------------------------
# LOGIN DECORATOR
# -------------------------------------------------------
def login_required(role=None):
    def wrapper(func):
        def check(*args, **kwargs):
            if "user" not in session:
                return redirect("/login")
            if role and session["user"]["role"] != role:
                abort(403)
            return func(*args, **kwargs)
        check.__name__ = func.__name__
        return check
    return wrapper

# -------------------------------------------------------
# UTILS
# -------------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def read_file_text(path):
    ext = path.rsplit(".", 1)[1].lower()
    if ext == "txt":
        return open(path, "r", encoding="utf-8", errors="ignore").read()
    return ""

def summarize_text(text):
    text = text[:4000]

    try:
        res = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Bạn là AI tóm tắt tài liệu."},
                {"role": "user", "content": f"Hãy tóm tắt ngắn gọn:\n{text}"}
            ]
        )
        return res.choices[0].message.content
    except:
        return "(Không thể tóm tắt bằng AI)"

def ai_answer(question, context_text):
    msg = [
        {"role": "system", "content": "Bạn là chatbot hỗ trợ trả lời theo tài liệu Chi Bộ."},
        {"role": "user", "content": f"Ngữ cảnh tài liệu:\n{context_text}\n\nCâu hỏi: {question}"}
    ]
    try:
        res = client.chat.completions.create(model="gpt-4.1-mini", messages=msg)
        return res.choices[0].message.content
    except:
        return "AI không phản hồi, vui lòng thử lại."

def tavily_search(question):
    try:
        result = tavily.search(query=question, max_results=3)
        return "\n".join([i["content"] for i in result["results"]])
    except:
        return ""

# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------

@app.route("/")
def home():
    return redirect("/login")


# ---------------------- LOGIN ----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        if u in USERS and USERS[u]["password"] == p:
            session["user"] = {"username": u, "role": USERS[u]["role"]}
            if USERS[u]["role"] == "admin":
                return redirect("/admin")
            if USERS[u]["role"] == "bithu":
                return redirect("/chi_bo")
            return redirect("/dang_vien")
        else:
            error = "Sai tài khoản hoặc mật khẩu"

    html = f"""
    <div class="col-md-4 mx-auto">
        <h3 class="text-center">Đăng nhập</h3>
        <form method="post">
            <label>Tài khoản</label>
            <input class="form-control" name="username" required>
            <label class="mt-2">Mật khẩu</label>
            <input class="form-control" type="password" name="password" required>
            <button class="btn btn-primary mt-3 w-100">Đăng nhập</button>
        </form>

        <p class="text-danger mt-2">{error}</p>
    </div>
    """
    return render_template_string(base_template(html))


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------------- ADMIN ----------------------
@app.route("/admin")
@login_required("admin")
def admin_home():
    html = """
    <h3>Quản lý người dùng</h3>
    <table class="table table-bordered">
      <tr><th>Tài khoản</th><th>Vai trò</th></tr>
      {% for u,info in users.items() %}
      <tr><td>{{u}}</td><td>{{info.role}}</td></tr>
      {% endfor %}
    </table>
    """
    return render_template_string(base_template(html), users=USERS)


# ---------------------- CHI BỘ (BÍ THƯ) ----------------------
@app.route("/chi_bo", methods=["GET", "POST"])
@login_required("bithu")
def chi_bo():
    if request.method == "POST":
        noi_dung = request.form["noi_dung"]
        SINH_HOAT.append(noi_dung)

    html = """
    <h3>Hoạt động Chi Bộ</h3>

    <form method="post">
      <textarea class="form-control" name="noi_dung" required></textarea>
      <button class="btn btn-success mt-2">Thêm hoạt động</button>
    </form>

    <h4 class="mt-4">Danh sách hoạt động</h4>
    <ul>
      {% for x in sinhhoat %}
      <li>{{x}}</li>
      {% endfor %}
    </ul>

    <h4 class="mt-4">Nhận xét Đảng viên</h4>

    <ul>
      {% for dv in dangvien %}
        <li>
          <a href="/nhan_xet/{{dv}}">Nhận xét {{dv}}</a>
        </li>
      {% endfor %}
    </ul>
    """
    return render_template_string(base_template(html),
                                  sinhhoat=SINH_HOAT,
                                  dangvien=[u for u in USERS if USERS[u]["role"] == "dangvien"])


# ---------------------- NHẬN XÉT ĐẢNG VIÊN ----------------------
@app.route("/nhan_xet/<dv>", methods=["GET", "POST"])
@login_required("bithu")
def nhan_xet(dv):
    if dv not in USERS or USERS[dv]["role"] != "dangvien":
        abort(404)

    if request.method == "POST":
        ND = request.form["noidung"]
        NHAN_XET[dv] = ND

    html = f"""
    <h3>Nhận xét Đảng viên: {dv}</h3>
    <form method="post">
      <textarea class="form-control" name="noidung" required>{NHAN_XET.get(dv,"")}</textarea>
      <button class="btn btn-primary mt-3">Lưu</button>
    </form>
    """
    return render_template_string(base_template(html))


# ---------------------- ĐẢNG VIÊN ----------------------
@app.route("/dang_vien")
@login_required("dangvien")
def dang_vien():
    dv = session["user"]["username"]

    html = """
    <h3>Trang Đảng viên</h3>

    <h4>Nhận xét của Bí thư</h4>
    <div class="border p-3">{{ nx or "Chưa có nhận xét." }}</div>

    <h4 class="mt-4">Hoạt động chung</h4>
    <ul>
    {% for x in sinhhoat %}
      <li>{{x}}</li>
    {% endfor %}
    </ul>
    """
    return render_template_string(base_template(html),
                                  nx=NHAN_XET.get(dv),
                                  sinhhoat=SINH_HOAT)


# ---------------------- UPLOAD TÀI LIỆU ----------------------
@app.route("/upload", methods=["GET", "POST"])
@login_required()
def upload():
    msg = ""
    if request.method == "POST":
        if "file" not in request.files:
            msg = "Không có file!"
        else:
            f = request.files["file"]
            if f and allowed_file(f.filename):
                filename = secure_filename(f.filename)
                path = os.path.join(UPLOAD_FOLDER, filename)
                f.save(path)

                content = read_file_text(path)
                summary = summarize_text(content)

                DOCS[filename] = {
                    "uploader": session["user"]["username"],
                    "summary": summary,
                    "content": content
                }
                msg = "Tải lên thành công!"
            else:
                msg = "File không hợp lệ!"

    html = f"""
    <h3>Upload tài liệu & tóm tắt AI</h3>

    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" class="form-control">
      <button class="btn btn-success mt-3">Tải lên</button>
    </form>

    <p class="text-danger mt-2">{msg}</p>
    """
    return render_template_string(base_template(html))


@app.route("/docs")
@login_required()
def docs_list():
    html = """
    <h3>Danh sách tài liệu</h3>
    <table class="table table-bordered">
      <tr><th>Tài liệu</th><th>Tóm tắt</th><th>Người tải lên</th></tr>
      {% for fn, info in docs.items() %}
      <tr>
        <td><a href="/docs/{{fn}}">{{fn}}</a></td>
        <td>{{info.summary}}</td>
        <td>{{info.uploader}}</td>
      </tr>
      {% endfor %}
    </table>
    """
    return render_template_string(base_template(html), docs=DOCS)


@app.route("/docs/<fn>")
@login_required()
def docs_view(fn):
    if fn not in DOCS:
        abort(404)

    info = DOCS[fn]
    html = f"""
    <h3>{fn}</h3>
    <p><b>Người tải lên:</b> {info['uploader']}</p>
    <h5>Tóm tắt AI</h5>
    <div class="border p-3">{info['summary']}</div>

    <h5 class="mt-4">Nội dung (trích)</h5>
    <pre class="border p-3" style="white-space: pre-wrap;">
{info['content'][:2000]}
    </pre>

    """
    return render_template_string(base_template(html))


# ---------------------- CHAT AI ----------------------
@app.route("/chat", methods=["GET", "POST"])
@login_required()
def chat():
    answer = ""
    question = ""
    context = ""

    if request.method == "POST":
        question = request.form["question"]

        # tìm tài liệu liên quan
        for fn, info in DOCS.items():
            if re.search(r".*" , info["summary"], re.I):
                context += f"\n--- {fn} ---\n{info['summary']}\n"

        # nếu không có tài liệu, dùng Tavily
        if not context.strip():
            web = tavily_search(question)
            context = web if web else "Không tìm thấy thông tin ngoài."

        answer = ai_answer(question, context)

    html = """
    <h3>Chatbot AI</h3>
    <form method="post">
      <input class="form-control" name="question" placeholder="Nhập câu hỏi..." required>
      <button class="btn btn-primary mt-3">Hỏi</button>
    </form>

    {% if answer %}
    <div class="alert alert-info mt-3">{{answer}}</div>
    {% endif %}
    """
    return render_template_string(base_template(html), answer=answer)


# ---------------------- RUN ----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
