import os
from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from utils.ai_utils import chat_with_context

app = FastAPI(title="AI Chatbot Backend", version="1.0.0")

# Cho phép CORS để frontend (HTML/JS) gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # có thể thay bằng domain của bạn khi deploy
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route test
@app.get("/")
def root():
    return {"message": "AI backend is running on Render 🚀"}


# API chat với AI
@app.post("/chat")
async def chat(prompt: str = Form(...), context: str = Form("")):
    """
    Nhận prompt + context từ frontend và trả về câu trả lời AI
    """
    try:
        answer = chat_with_context(prompt, context)
        return {"answer": answer}
    except Exception as e:
        return {"error": str(e)}


# API upload file (ví dụ: PDF, CSV, v.v.)
@app.post("/upload")
async def upload_file(file: UploadFile):
    """
    Nhận file upload từ frontend.
    (Hiện tại chỉ trả về tên file, bạn có thể xử lý thêm ở utils/pdf_reader.py hoặc vector_store.py)
    """
    try:
        contents = await file.read()
        size_kb = round(len(contents) / 1024, 2)
        return {"filename": file.filename, "size_kb": size_kb}
    except Exception as e:
        return {"error": str(e)}


# Run local (Render sẽ tự chạy bằng uvicorn khi deploy)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
