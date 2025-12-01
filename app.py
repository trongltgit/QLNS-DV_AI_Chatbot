from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from openai import OpenAI
import os
import json
import re

# Thư viện đọc file
from pypdf import PdfReader
import docx
import openpyxl

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Lưu tạm context trong bộ nhớ (Render free đủ dùng)
CURRENT_CONTEXT = ""
CURRENT_FILENAME = ""

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
                text += page.extract_text() or ""
        elif ext == "docx":
            doc = docx.Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext == "xlsx":
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                row_text = [str(cell) for cell in row if cell is not None]
                text += " | ".join(row_text) + "\n"
    except:
        text = "Không thể đọc nội dung file này."

    return text

def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 100):
    """Tự viết hàm split text - thay thế LangChain"""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks if chunks else [""]

def retrieve_relevant_chunks(query: str, chunks: list):
    """Tìm 3 đoạn liên quan nhất bằng từ khóa đơn giản"""
    query_lower = query.lower()
    scored = []
    for chunk in chunks:
        score = sum(1 for word in query_lower.split() if word in chunk.lower())
        if score > 0:
            scored.append((score, chunk))
    scored.sort(reverse=True)
    return "\n\n".join([chunk for _, chunk in scored[:3]])

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global CURRENT_CONTEXT, CURRENT_FILENAME
    filename = file.filename
    save_path = f"static/{filename}"

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    full_text = extract_text_from_file(save_path, filename)
    
    if len(full_text.strip()) < 50:
        return JSONResponse({"error": "File rỗng hoặc không đọc được nội dung"})

    # Tóm tắt bằng GPT
    try:
        summary_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tóm tắt ngắn gọn bằng tiếng Việt, dưới 200 từ."},
                {"role": "user", "content": full_text[:8000]}
            ],
            temperature=0.3
        )
        summary = summary_resp.choices[0].message.content
    except:
        summary = "Không thể tạo tóm tắt (vượt giới hạn hoặc lỗi API)."

    # Lưu toàn bộ text để dùng cho RAG
    CURRENT_CONTEXT = full_text
    CURRENT_FILENAME = filename

    return JSONResponse({
        "filename": filename,
        "summary": summary
    })

@app.post("/chat")
async def chat_endpoint(prompt: str = Form(...), history: str = Form("[]")):
    global CURRENT_CONTEXT

    try:
        messages = [
            {"role": "system", "content": "Bạn là trợ lý AI thông minh, trả lời bằng tiếng Việt, ngắn gọn, chính xác."}
        ]

        # Nếu có tài liệu → thêm context liên quan
        if CURRENT_CONTEXT:
            chunks = split_text_into_chunks(CURRENT_CONTEXT, 1000, 100)
            relevant = retrieve_relevant_chunks(prompt, chunks)
            if relevant.strip():
                messages.append({"role": "system", "content": f"Dựa vào tài liệu sau để trả lời:\n{relevant}"})

        # Thêm lịch sử chat
        history_list = json.loads(history)
        messages.extend(history_list)

        # Thêm câu hỏi hiện tại
        messages.append({"role": "user", "content": prompt})

        # Gọi OpenAI
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7
        )
        answer = resp.choices[0].message.content

        # Cập nhật history (loại bỏ system messages)
        updated_history = [m for m in messages if m["role"] != "system"]
        return JSONResponse({
            "response": answer,
            "updated_history": json.dumps(updated_history)
        })

    except Exception as e:
        return JSONResponse({"error": f"Lỗi: {str(e)}"})
