from fastapi import FastAPI, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
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

# Static files (css, js)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Trang chủ
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Upload PDF và lưu chunks
@app.post("/upload")
async def upload_file(file: UploadFile):
    file_path = f"uploads/{file.filename}"
    os.makedirs("uploads", exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    chunks = extract_chunks(file_path)
    store_chunks(chunks)
    return {"status": "ok", "chunks": len(chunks)}

# Chat với tài liệu
@app.post("/chat")
async def chat(query: str = Form(...)):
    context = search_chunks(query)
    answer = chat_with_context(query, context)
    return {"answer": answer, "context": context}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render truyền PORT
    uvicorn.run(app, host="0.0.0.0", port=port)
