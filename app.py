# app.py
from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os

from utils import vector_store, ai_utils
from utils.pdf_reader import extract_chunks  # nếu bạn có pdf_reader.py như trước

app = FastAPI()

# Cho phép frontend gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # bạn có thể thay bằng ["https://domain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <h2>AI Chatbot Demo</h2>
    <form action="/upload" enctype="multipart/form-data" method="post">
      <input type="file" name="file"/>
      <button type="submit">Upload</button>
    </form>
    <br/>
    <form action="/chat" method="post">
      <input type="text" name="question" placeholder="Nhập câu hỏi..."/>
      <button type="submit">Hỏi</button>
    </form>
    """


@app.post("/upload")
async def upload_file(file: UploadFile):
    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Trích xuất & lưu chunks vào vector_store
        chunks = extract_chunks(file_path, chunk_size=500)
        vector_store.store_chunks(chunks)

        return {"status": "success", "message": f"Đã tải và lưu file {file.filename}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/chat")
async def chat(question: str = Form(...)):
    try:
        answer = ai_utils.answer_question(question)
        return {"question": question, "answer": answer}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/summarize")
async def summarize(question: str = Form(...)):
    try:
        # lấy tất cả chunks đã lưu
        context = "\n".join(vector_store.stored_chunks)
        summary = ai_utils.summarize_text(context)
        return {"summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
