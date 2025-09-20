from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import os
import uvicorn

from utils.pdf_reader import extract_chunks
from utils.vector_store import store_chunks, search_chunks
from utils.ai_utils import chat_with_context

app = FastAPI()

# CORS cho frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static (index.html + css)
app.mount("/static", StaticFiles(directory="static"), name="static")


# --------- API Routes ---------
@app.post("/api/upload")
async def upload_file(file: UploadFile):
    """Upload PDF và lưu thành chunks"""
    if not file.filename.endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Chỉ hỗ trợ file PDF"})

    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", file.filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    chunks = extract_chunks(file_path)
    store_chunks(chunks)

    return {"status": "ok", "message": f"Đã upload {file.filename}", "chunks": len(chunks)}


@app.post("/api/ask")
async def ask_question(question: str = Form(None)):
    """
    Chat với tài liệu PDF.
    Frontend gửi JSON { "question": "..." } thì mình parse ra.
    """
    if not question:
        return JSONResponse(status_code=400, content={"error": "Thiếu câu hỏi"})

    context = search_chunks(question)
    answer = chat_with_context(question, context)

    return {"answer": answer, "sources": context}


@app.get("/")
async def serve_index():
    """Serve trang index.html"""
    return FileResponse("static/index.html")


# --------- Main entry ---------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render sẽ truyền PORT
    uvicorn.run(app, host="0.0.0.0", port=port)
