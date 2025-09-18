import os
from fastapi import FastAPI, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from utils.pdf_reader import extract_chunks
from utils.vector_store import build_faiss_index, search_faiss
from utils.ai_utils import ask_ai
from pydantic import BaseModel

UPLOAD_DIR = "uploads"
DB_DIR = "db"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class Question(BaseModel):
    question: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/upload")
async def upload_pdf(file: UploadFile):
    if not file.filename.endswith(".pdf"):
        return JSONResponse({"error": "Chỉ hỗ trợ PDF"}, status_code=400)

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    chunks = extract_chunks(file_path)
    build_faiss_index(chunks, file.filename)

    return {"message": f"Đã xử lý {file.filename} với {len(chunks)} đoạn."}

@app.post("/api/ask")
async def ask_question(q: Question):
    question = q.question
    docs = search_faiss(question)
    answer = ask_ai(question, docs)
    return {"answer": answer, "sources": docs}
