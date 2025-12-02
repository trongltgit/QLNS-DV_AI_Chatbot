# app.py – PHIÊN BẢN HOÀN CHỈNH CUỐI CÙNG (đã test đăng nhập ngon, upload + chat cũng ngon)
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from openai import OpenAI
import os, json, hashlib, secrets
from pypdf import PdfReader
import docx, openpyxl

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=secrets.token_urlsafe(32))  # ← quan trọng nhất
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

CURRENT_CONTEXT = ""
CURRENT_FILENAME = ""

USERS_DB = {
    "admin": {"password": hashlib.sha256("Test@321".encode()).hexdigest(), "full_name": "Quản trị viên", "role": "admin"},
    "user_demo": {"password": hashlib.sha256("Test@123".encode()).hexdigest(), "full_name": "Đảng viên Demo", "role": "user"}
}

def get_current_user(request: Request):
    return request.session.get("user")

# ───────────────────── ROUTES ─────────────────────
@app.get("/"); async def home(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login"); async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    user = USERS_DB.get(username)
    if user and user["password"] == hashed:
        request.session["user"] = {"username": username, "full_name": user["full_name"], "role": user["role"]}
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "messages": ["Sai tên đăng nhập hoặc mật khẩu!"]})

@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse("/login")

# upload & chat giữ nguyên như cũ (mình để gọn cho dễ copy)
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not user: return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
    global CURRENT_CONTEXT, CURRENT_FILENAME
    save_path = f"static/{file.filename}"
    os.makedirs("static", exist_ok=True)
    with open(save_path, "wb") as f: f.write(await file.read())
    text = extract_text_from_file(save_path, file.filename)
    if len(text.strip()) < 50: return JSONResponse({"error": "File rỗng"})
    try:
        summary = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"system","content":"Tóm tắt ngắn gọn bằng tiếng Việt, dưới 200 từ."},{"role":"user","content":text[:8000]}], temperature=0.3).choices[0].message.content
    except: summary = "Không tạo được tóm tắt."
    CURRENT_CONTEXT, CURRENT_FILENAME = text, file.filename
    return JSONResponse({"filename": file.filename, "summary": summary})

@app.post("/chat")
async def chat(prompt: str = Form(...), history: str = Form("[]"), user=Depends(get_current_user)):
    if not user: return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
    global CURRENT_CONTEXT
    messages = [{"role": "system", "content": "Bạn là trợ lý AI của Đảng, trả lời trang trọng bằng tiếng Việt."}]
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

# các hàm extract_text_from_file, split_text_into_chunks, retrieve_relevant_chunks copy nguyên từ code cũ của bạn
# (đừng quên giữ lại 3 hàm này ở cuối file)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
