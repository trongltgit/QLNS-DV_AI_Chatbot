import os
from fastapi import FastAPI, UploadFile, Form, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from PyPDF2 import PdfReader
from openai import OpenAI

# Cấu hình OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Khởi tạo app
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Bộ nhớ tạm
docs_db = {}  # filename -> {"content":..., "summary":...}


def summarize_text(text: str) -> str:
    """Tóm tắt văn bản sử dụng OpenAI"""
    if not text.strip():
        return "Không có nội dung để tóm tắt."
    prompt = f"Tóm tắt ngắn gọn tài liệu sau:\n\n{text[:4000]}"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Bạn là một trợ lý tóm tắt tài liệu."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/docs")
async def list_docs():
    return {"docs": list(docs_db.keys())}


@app.post("/api/upload")
async def upload_file(file: UploadFile):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    # Đọc PDF
    content = ""
    if file.filename.lower().endswith(".pdf"):
        reader = PdfReader(file_path)
        for page in reader.pages:
            content += page.extract_text() or ""
    else:
        content = "(Chỉ hỗ trợ PDF trong demo)"

    summary = summarize_text(content)
    docs_db[file.filename] = {"content": content, "summary": summary}
    return {"message": "Upload thành công", "filename": file.filename, "summary": summary}


@app.post("/api/chat")
async def chat_with_doc(
    question: str = Form(...),
    filename: str = Form(...)
):
    data = docs_db.get(filename)
    if not data:
        return JSONResponse({"answer": "Không tìm thấy tài liệu."}, status_code=404)

    context = f"Tóm tắt: {data['summary']}\n\nNội dung: {data['content'][:4000]}"
    prompt = f"Dựa trên tài liệu sau, trả lời câu hỏi của người dùng.\n\n{context}\n\nCâu hỏi: {question}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Bạn là trợ lý ảo thông minh, trả lời dựa trên tài liệu."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=400,
    )
    answer = response.choices[0].message.content.strip()
    return {"answer": answer}
