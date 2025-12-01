from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException
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
app = FastAPI(title="HỆ THỐNG QLNS - ĐẢNG VIÊN")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Biến toàn cục cho RAG
CURRENT_CONTEXT = ""
CURRENT_FILENAME = ""

# ====================== DANH SÁCH USER (có thể mở rộng sau) ======================
USERS_DB = {
    "admin": {
        "password": hashlib.sha256("Test@321".encode()).hexdigest(),
        "full_name": "Quản trị viên Hệ thống",
        "role": "admin"
    },
    "user_demo": {
        "password": hashlib.sha256("Test@123".encode()).hexdigest(),
        "full_name": "Đảng viên Demo",
        "role": "user"
    },
    "leader1": {
        "password": hashlib.sha256("Test@123".encode()).hexdigest(),
        "full_name": "Trưởng Chi bộ 1",
        "role": "leader"
    }
}

# ====================== XÁC THỰC NGƯỜI DÙNG ======================
async def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "):
        return None
    try:
        encoded = auth.split(" ")[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
        hashed = hashlib.sha256(password.encode()).hexdigest()
        user = USERS_DB.get(username)
        if user and user["password"] == hashed:
            return {"username": username, **user}
    except:
        pass
    return None

# ====================== HÀM HỖ TRỢ RAG ======================
def extract_text_from_file(file_path: str, filename: str) -> str:
    ext = filename.lower().split(".")[-1]
    text = ""
    try:
        if ext == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif ext == "pdf":
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
        elif ext == "docx":
            doc = docx.Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext == "xlsx":
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                row_text = [str(cell) if cell is not None else "" for cell in row]
                text += " | ".join(row_text) + "\n"
    except Exception as e:
        text = f"Không thể đọc file: {str(e)}"
    return text

def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 100):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
        if i >= len(words) and chunks:
            break
    return chunks if chunks else [""]

def retrieve_relevant_chunks(query: str, chunks: list):
    if not chunks:
        return ""
    query_lower = query.lower()
    scored = []
    for chunk in chunks:
        score = sum(1 for word in query_lower.split() if word in chunk.lower())
        if score > 0:
            scored.append((score, chunk))
    scored.sort(reverse=True, key=lambda x: x[0])
    return "\n\n".join([chunk for _, chunk in scored[:3]])

# ====================== ROUTES ======================
@app.get("/")
async def home(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "messages": []
    })

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "messages": []
    })

@app.get("/logout")
async def logout():
    response = RedirectResponse("/login")
    return response

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")
    
    global CURRENT_CONTEXT, CURRENT_FILENAME
    filename = file.filename
    save_path = f"static/{filename}"
    
    content = await file.read()
    os.makedirs("static", exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(content)

    full_text = extract_text_from_file(save_path, filename)
    if len(full_text.strip()) < 50:
        return JSONResponse({"error": "File rỗng hoặc không đọc được nội dung"})

    try:
        summary_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tóm tắt ngắn gọn bằng tiếng Việt, dưới 200 từ."},
                {"role": "user", "content": full_text[:8000]}
            ],
            temperature=0.3
        )
        summary = summary_resp.choices[0].message.content.strip()
    except Exception as e:
        summary = "Không thể tạo tóm tắt (lỗi API)."

    CURRENT_CONTEXT = full_text
    CURRENT_FILENAME = filename

    return JSONResponse({"filename": filename, "summary": summary})

@app.post("/chat")
async def chat_endpoint(prompt: str = Form(...), history: str = Form("[]"), user=Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")

    global CURRENT_CONTEXT
    try:
        messages = [{"role": "system", "content": "Bạn là trợ lý AI chuyên về Đảng, trả lời bằng tiếng Việt, ngắn gọn, chính xác."}]

        if CURRENT_CONTEXT:
            chunks = split_text_into_chunks(CURRENT_CONTEXT)
            relevant = retrieve_relevant_chunks(prompt, chunks)
            if relevant.strip():
                messages.append({"role": "system", "content": f"Dựa vào tài liệu sau để trả lời:\n{relevant}"})

        history_list = json.loads(history)
        messages.extend(history_list)
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7
        )
        answer = resp.choices[0].message.content

        updated_history = [m for m in messages if m["role"] != "system"]

        return JSONResponse({
            "response": answer,
            "updated_history": json.dumps(updated_history, ensure_ascii=False)
        })
    except Exception as e:
        return JSONResponse({"error": f"Lỗi hệ thống: {str(e)}"}, status_code=500)

# ====================== CHẠY SERVER (QUAN TRỌNG NHẤT!) ======================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)
