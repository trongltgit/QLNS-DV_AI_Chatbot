from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os
import json
import hashlib
import base64

# Thư viện đọc file
from pypdf import PdfReader
import docx
import openpyxl

# ====================== KHỞI TẠO ======================
app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Biến RAG
CURRENT_CONTEXT = ""
CURRENT_FILENAME = ""

# ====================== USER DATABASE (chỉ để lại 2 user mặc định) ======================
USERS_DB = {
    "admin": {
        "password": hashlib.sha256("Test@321".encode()).hexdigest(),
        "full_name": "Quản trị viên",
        "role": "admin"
    },
    "user_demo": {
        "password": hashlib.sha256("Test@123".encode()).hexdigest(),
        "full_name": "Đảng viên Demo",
        "role": "user"
    }
    # Admin sẽ thêm user thường sau → không để sẵn
}

# ====================== XÁC THỰC ======================
def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Basic "):
        try:
            encoded = auth.split(" ")[1]
            decoded = base64.b64decode(encoded).decode()
            username, password = decoded.split(":", 1)
            user = USERS_DB.get(username)
            if user and user["password"] == hashlib.sha256(password.encode()).hexdigest():
                return {"username": username, **user}
        except: pass
    return None

# ====================== HỖ TRỢ RAG ======================
def extract_text_from_file(file_path: str, filename: str) -> str:
    # (giữ nguyên hàm cũ của bạn – đã test ổn)
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
    except: text = "Không đọc được file."
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
    scored = [(sum(1 for w in query_lower.split() if w in c.lower()), c) for c in chunks if any(w in c.lower() for w in query_lower.split())]
    scored.sort(reverse=True)
    return "\n\n".join([c for _, c in scored[:3]])

# ====================== ROUTES ======================
@app.get("/")
async def home(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "messages": []})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "messages": []})

# QUAN TRỌNG: THÊM POST /login ĐỂ XỬ LÝ FORM
@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    user = USERS_DB.get(username)
    if user and user["password"] == hashed:
        # Tạo Basic Auth header giả để client tự redirect
        response = RedirectResponse("/", status_code=302)
        auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
        response.headers["Authorization"] = f"Basic {auth_str}"
        return response
    return templates.TemplateResponse("login.html", {
        "request": request,
        "messages": ["Sai tên đăng nhập hoặc mật khẩu!"]
    }, status_code=401)

@app.get("/logout")
async def logout():
    return RedirectResponse("/login")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not user: return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
    global CURRENT_CONTEXT, CURRENT_FILENAME
    filename = file.filename
    save_path = f"static/{filename}"
    os.makedirs("static", exist_ok=True)
    with open(save_path, "wb") as f:
        await file.seek(0)
        f.write(await file.read())
    full_text = extract_text_from_file(save_path, filename)
    if len(full_text.strip()) < 50:
        return JSONResponse({"error": "File rỗng"})
    try:
        summary = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Tóm tắt ngắn gọn bằng tiếng Việt, dưới 200 từ."},
                      {"role": "user", "content": full_text[:8000]}],
            temperature=0.3
        ).choices[0].message.content
    except: summary = "Không tạo được tóm tắt."
    CURRENT_CONTEXT, CURRENT_FILENAME = full_text, filename
    return JSONResponse({"filename": filename, "summary": summary})

@app.post("/chat")
async def chat(prompt: str = Form(...), history: str = Form("[]"), user=Depends(get_current_user)):
    if not user: return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
    global CURRENT_CONTEXT
    messages = [{"role": "system", "content": "Bạn là trợ lý AI thông minh của Đảng, trả lời bằng tiếng Việt."}]
    if CURRENT_CONTEXT:
        chunks = split_text_into_chunks(CURRENT_CONTEXT)
        relevant = retrieve_relevant_chunks(prompt, chunks)
        if relevant: messages.append({"role": "system", "content": f"Dựa vào tài liệu:\n{relevant}"})
    messages.extend(json.loads(history))
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, temperature=0.7)
    answer = resp.choices[0].message.content
    updated = [m for m in messages if m["role"] != "system"]
    return JSONResponse({"response": answer, "updated_history": json.dumps(updated, ensure_ascii=False)})

# CHẠY SERVER
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
