from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from openai import OpenAI
import os

# Thư viện đọc file
from pypdf import PdfReader
import docx
import openpyxl

# Khởi tạo client với OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# ===== CORS Middleware =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # cho phép tất cả domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def extract_text_from_file(file_path: str, filename: str) -> str:
    """Trích xuất text từ file theo định dạng"""
    ext = filename.lower().split(".")[-1]
    text = ""

    if ext == "txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    elif ext == "pdf":
        reader = PdfReader(file_path)
        for page in reader.pages[:5]:  # chỉ lấy 5 trang đầu cho nhẹ
            text += page.extract_text() or ""
    elif ext == "docx":
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
    elif ext == "xlsx":
        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            text += " ".join([str(cell) for cell in row if cell]) + "\n"
    else:
        text = "⚠️ Định dạng file chưa hỗ trợ trích xuất nội dung."

    return text[:2000]  # giới hạn để tránh quá dài


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename
    save_path = f"static/{filename}"

    with open(save_path, "wb") as f:
        f.write(await file.read())

    try:
        content = extract_text_from_file(save_path, filename)
        if not content.strip():
            raise ValueError("Không đọc được nội dung file")

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là AI chuyên tóm tắt văn bản ngắn gọn."},
                {"role": "user", "content": f"Hãy tóm tắt nội dung sau:\n{content}"}
            ]
        )
        summary = completion.choices[0].message.content
    except Exception as e:
        summary = f"❌ Không thể tóm tắt file: {e}"

    return JSONResponse({"filename": filename, "summary": summary})


@app.post("/chat")
async def chat_endpoint(prompt: str = Form(...), context: str = Form(None)):
    try:
        messages = [
            {"role": "system", "content": "Bạn là AI trợ lý thông minh, luôn trả lời rõ ràng."}
        ]
        if context:
            messages.append({"role": "system", "content": f"Ngữ cảnh từ file: {context}"})
        messages.append({"role": "user", "content": prompt})

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        response_text = completion.choices[0].message.content
    except Exception as e:
        response_text = f"❌ AI API error: {e}"

    return JSONResponse({"response": response_text})
