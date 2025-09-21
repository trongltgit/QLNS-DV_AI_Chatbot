# app.py
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os, re
import openai
from pypdf import PdfReader
import docx
import pandas as pd

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Thiết lập model & key từ biến môi trường
openai.api_key = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")  # đổi nếu cần

def safe_filename(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.basename(name))

async def extract_text_from_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    text = ""
    try:
        if ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif ext == ".pdf":
            reader = PdfReader(path)
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n".join(pages)
        elif ext == ".docx":
            doc = docx.Document(path)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext in [".xls", ".xlsx", ".csv"]:
            if ext == ".csv":
                df = pd.read_csv(path, dtype=str, encoding="utf-8", errors="ignore")
            else:
                df = pd.read_excel(path, engine="openpyxl", dtype=str)
            text = df.fillna("").to_string(index=False)
        else:
            text = ""
    except Exception as e:
        # không ném lỗi cho user demo, trả chuỗi rỗng
        text = ""
    return text

def truncate_text(s: str, max_chars: int = 15000) -> str:
    return s if len(s) <= max_chars else s[:max_chars]

async def summarize_text(text: str) -> str:
    if not openai.api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY chưa được thiết lập trên server.")
    text_to_send = truncate_text(text, max_chars=15000)
    user_prompt = (
        "Bạn là một trợ lý tóm tắt tiếng Việt. "
        "Hãy tóm tắt ngắn gọn (khoảng 100-300 từ), liệt kê các điểm chính và kết luận nếu có.\n\n"
        f"{text_to_send}"
    )
    try:
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[
                {"role":"system","content":"Bạn là trợ lý tóm tắt chuyên nghiệp bằng tiếng Việt."},
                {"role":"user","content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.2,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(Lỗi khi gọi OpenAI: {str(e)})"

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = safe_filename(file.filename)
    save_path = os.path.join(UPLOAD_DIR, filename)
    contents = await file.read()
    with open(save_path, "wb") as f:
        f.write(contents)

    text = await extract_text_from_file(save_path)
    if text:
        summary = await summarize_text(text)
    else:
        summary = "Không thể trích xuất văn bản từ tệp hoặc tệp rỗng."

    return JSONResponse({"filename": filename, "summary": summary})

@app.post("/chat")
async def chat_endpoint(prompt: str = Form(...), context: str = Form(None)):
    if not openai.api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY chưa được thiết lập trên server.")
    messages = [
        {"role":"system","content":"Bạn là một trợ lý AI trả lời bằng tiếng Việt, ngắn gọn, rõ ràng."}
    ]
    if context:
        # gửi tóm tắt như ngữ cảnh hệ thống để model sử dụng
        shortened = truncate_text(context, max_chars=4000)
        messages.append({"role":"system","content": f"Sử dụng tóm tắt tài liệu sau làm ngữ cảnh: {shortened}"})
    messages.append({"role":"user","content": prompt})

    try:
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=messages,
            max_tokens=800,
            temperature=0.2
        )
        answer = resp["choices"][0]["message"]["content"].strip()
        return JSONResponse({"response": answer})
    except Exception as e:
        return JSONResponse({"error": f"AI API error: {str(e)}"})
