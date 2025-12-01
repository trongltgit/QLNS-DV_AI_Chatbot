from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from openai import OpenAI
import os
import json

# Thư viện đọc file
from pypdf import PdfReader
import docx
import openpyxl

# LangChain cho RAG
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings  # Để embed nếu cần, nhưng dùng simple cho giờ
from langchain.docstore.document import Document

# Khởi tạo client với OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# ===== CORS Middleware =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global để lưu context (thay bằng Redis/session nếu production)
file_contexts = {}  # {filename: full_text}

def extract_text_from_file(file_path: str, filename: str) -> str:
    """Trích xuất text từ file theo định dạng"""
    ext = filename.lower().split(".")[-1]
    text = ""

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
            text += " ".join([str(cell) for cell in row if cell]) + "\n"
    else:
        text = "⚠️ Định dạng file chưa hỗ trợ."

    return text

def simple_retrieve_relevant_chunks(query: str, full_text: str, chunk_size=500) -> str:
    """Simple RAG: Split text và retrieve chunks chứa keywords từ query"""
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=50)
    chunks = splitter.split_text(full_text)
    relevant = []
    query_words = set(query.lower().split())
    for chunk in chunks:
        if any(word in chunk.lower() for word in query_words):
            relevant.append(chunk)
    return "\n\n".join(relevant[:3])  # Top 3 chunks

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename
    save_path = f"static/{filename}"

    content_bytes = await file.read()
    with open(save_path, "wb") as f:
        f.write(content_bytes)

    try:
        full_text = extract_text_from_file(save_path, filename)
        if not full_text.strip():
            raise ValueError("Không đọc được nội dung file")
        
        # Lưu full text cho RAG
        file_contexts[filename] = full_text
        
        # Tóm tắt cho display
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là AI chuyên tóm tắt văn bản ngắn gọn bằng tiếng Việt."},
                {"role": "user", "content": f"Tóm tắt ngắn gọn (dưới 200 từ): {full_text[:4000]}"}
            ]
        )
        summary = completion.choices[0].message.content
    except Exception as e:
        summary = f"❌ Không thể tóm tắt: {str(e)}"
        full_text = ""

    return JSONResponse({"filename": filename, "summary": summary, "full_context_saved": True})

@app.post("/chat")
async def chat_endpoint(
    prompt: str = Form(...), 
    context_filename: str = Form(None),  # Thay vì context str, dùng filename để lấy full_text
    history: str = Form(None)  # JSON string của history messages
):
    try:
        messages = [{"role": "system", "content": "Bạn là AI trợ lý thông minh, trả lời rõ ràng bằng tiếng Việt."}]
        
        # Lấy context từ file nếu có
        if context_filename and context_filename in file_contexts:
            full_text = file_contexts[context_filename]
            relevant_context = simple_retrieve_relevant_chunks(prompt, full_text)
            if relevant_context:
                messages.append({"role": "system", "content": f"Ngữ cảnh từ tài liệu:\n{relevant_context}"})
            else:
                messages.append({"role": "system", "content": f"Tóm tắt tài liệu: {full_text[:500]}..."})
        
        # Thêm history nếu có (multi-turn)
        if history:
            history_list = json.loads(history)
            messages.extend(history_list)
        
        # Thêm user prompt
        messages.append({"role": "user", "content": prompt})

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        response_text = completion.choices[0].message.content
        
        # Return với history updated (cho frontend append)
        updated_history = messages[1:]  # Exclude system
        return JSONResponse({"response": response_text, "updated_history": json.dumps(updated_history)})
        
    except Exception as e:
        return JSONResponse({"error": f"❌ Lỗi: {str(e)}"})
