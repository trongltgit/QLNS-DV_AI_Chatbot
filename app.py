# app.py – FIX LỖI 500, THỨ TỰ THAM SỐ ĐÚNG, CHẠY NGON RENDER
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from openai import OpenAI
import os, json, hashlib, secrets
import json as json_lib  # Để lưu DB

from pypdf import PdfReader
import docx, openpyxl

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=secrets.token_urlsafe(32))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CURRENT_CONTEXT = ""
CURRENT_FILENAME = ""

# Load USERS_DB từ file JSON nếu có (persistent)
USERS_FILE = "users.json"
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        USERS_DB = json_lib.load(f)
else:
    USERS_DB = {
        "admin": {"password": hashlib.sha256("Test@321".encode()).hexdigest(), "full_name": "Quản trị viên", "role": "admin"},
        "user_demo": {"password": hashlib.sha256("Test@123".encode()).hexdigest(), "full_name": "Đảng viên Demo", "role": "user"}
    }
    # Lưu mặc định
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json_lib.dump(USERS_DB, f, ensure_ascii=False, indent=2)

def save_users_db():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json_lib.dump(USERS_DB, f, ensure_ascii=False, indent=2)

def get_current_user(request: Request):
    return request.session.get("user")

def require_admin(user):
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Chỉ admin mới được truy cập")

# ====================== RAG FUNCTIONS (GIỮ NGUYÊN) ======================
def extract_text_from_file(file_path: str, filename: str) -> str:
    ext = filename.lower().split(".")[-1]
    text = ""
    try:
        if ext == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f: text = f.read()
        elif ext == "pdf":
            reader = PdfReader(file_path)
            for page in reader.pages: text += (page.extract_text() or "") + "\n"
        elif ext == "docx":
            doc = docx.Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext == "xlsx":
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                row_text = [str(c) if c is not None else "" for c in row]
                text += " | ".join(row_text) + "\n"
    except Exception as e:
        text = f"Lỗi đọc file: {e}"
    return text

def split_text_into_chunks(text: str, chunk_size=1000, overlap=100):
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks or [""]

def retrieve_relevant_chunks(query: str, chunks: list):
    if not chunks: return ""
    query_lower = query.lower()
    scored = [(sum(1 for w in query_lower.split() if w in c.lower()), c) for c in chunks]
    scored.sort(reverse=True)
    return "\n\n".join([c for _, c in scored[:3]])

# ====================== ROUTES ======================
@app.get("/")
async def home(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    user_data = USERS_DB.get(username)
    if user_data and user_data["password"] == hashed:
        request.session["user"] = {"username": username, "full_name": user_data["full_name"], "role": user_data["role"]}
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Sai tài khoản hoặc mật khẩu!"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get("/user/profile")
async def user_profile(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("user_profile.html", {"request": request, "user": user})

# ====================== ADMIN PANEL (FIX COOKIES & THỨ TỰ) ======================
@app.get("/admin/users")
async def admin_users(request: Request, user=Depends(get_current_user)):
    require_admin(user)
    users_list = [{"username": k, **v} for k, v in USERS_DB.items()]
    success = request.session.pop("success", None)  # Lấy từ session thay cookies
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": user, "users": users_list, "success": success})

@app.post("/admin/users/add")
async def admin_add_user(
    username: str = Form(...), full_name: str = Form(...), password: str = Form(...), role: str = Form("user"),
    request: Request = None, user=Depends(get_current_user)  # ← FIX: Request SAU Form
):
    require_admin(user)
    if username in USERS_DB:
        request.session["error"] = "Username đã tồn tại!"
        return RedirectResponse("/admin/users", status_code=302)
    USERS_DB[username] = {
        "password": hashlib.sha256(password.encode()).hexdigest(),
        "full_name": full_name,
        "role": role
    }
    save_users_db()  # Lưu DB
    request.session["success"] = f"Đã thêm user {username} thành công!"
    return RedirectResponse("/admin/users", status_code=302)

@app.post("/admin/users/delete/{username}")
async def admin_delete_user(username: str, user=Depends(get_current_user)):
    require_admin(user)
    if username in USERS_DB and username != "admin":
        del USERS_DB[username]
        save_users_db()
    request.session["success"] = "Đã xóa user thành công!"
    return RedirectResponse("/admin/users", status_code=302)

@app.post("/admin/users/reset/{username}")
async def admin_reset_pass(username: str, user=Depends(get_current_user)):
    require_admin(user)
    if username in USERS_DB:
        USERS_DB[username]["password"] = hashlib.sha256("123456".encode()).hexdigest()
        save_users_db()
    request.session["success"] = "Đã reset mật khẩu về 123456!"
    return RedirectResponse("/admin/users", status_code=302)

# ====================== UPLOAD & CHAT (FIX "NO FILE") ======================
@app.post("/upload")
async def upload(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not user: return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
    global CURRENT_CONTEXT, CURRENT_FILENAME
    filename = file.filename
    if not filename or filename == "":
        return JSONResponse({"error": "Không có file được chọn! Vui lòng chọn file PDF/DOCX/TXT/XLSX."}, status_code=400)
    save_path = f"static/{filename}"
    os.makedirs("static", exist_ok=True)
    content = await file.read()
    with open(save_path, "wb") as f: f.write(content)
    
    text = extract_text_from_file(save_path, filename)
    if len(text.strip()) < 50:
        return JSONResponse({"error": "File rỗng hoặc không đọc được nội dung"}, status_code=400)
    
    try:
        summary = client.chat.completions.create(model="gpt-4o-mini", messages=[
            {"role": "system", "content": "Tóm tắt ngắn gọn bằng tiếng Việt, dưới 150 từ."},
            {"role": "user", "content": text[:8000]}
        ], temperature=0.3).choices[0].message.content
    except Exception as e:
        summary = f"Lỗi API: {str(e)[:100]}"
    
    CURRENT_CONTEXT, CURRENT_FILENAME = text, filename
    return JSONResponse({"filename": filename, "summary": summary})

@app.post("/chat")
async def chat(prompt: str = Form(""), history: str = Form("[]"), user=Depends(get_current_user)):
    if not user: return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
    global CURRENT_CONTEXT
    try: history_list = json_lib.loads(history)
    except: history_list = []
    
    messages = [{"role": "system", "content": "Bạn là trợ lý AI của Đảng Cộng sản Việt Nam. Trả lời trang trọng, chính xác, bằng tiếng Việt."}]
    if CURRENT_CONTEXT:
        chunks = split_text_into_chunks(CURRENT_CONTEXT)
        relevant = retrieve_relevant_chunks(prompt, chunks)
        if relevant:
            messages.append({"role": "system", "content": f"Dựa vào tài liệu:\n{relevant}"})
    
    messages.extend(history_list)
    if prompt.strip():
        messages.append({"role": "user", "content": prompt})
    
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.7)
        answer = resp.choices[0].message.content
    except Exception as e:
        answer = f"Lỗi kết nối OpenAI: {str(e)}"
    
    new_history = [m for m in messages if m["role"] != "system"]
    return JSONResponse({"response": answer, "updated_history": json_lib.dumps(new_history, ensure_ascii=False)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
