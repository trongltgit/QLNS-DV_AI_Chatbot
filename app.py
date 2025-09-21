from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from utils.file_reader import read_file
from utils.ai_utils import summarize_text, answer_question

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

uploaded_content = ""  # lưu nội dung file đã upload

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global uploaded_content
    try:
        content = read_file(file)
        uploaded_content = content
        summary = summarize_text(content)
        return JSONResponse({"filename": file.filename, "summary": summary})
    except Exception as e:
        return JSONResponse({"error": str(e)})

@app.post("/chat")
async def chat(prompt: str):
    if not uploaded_content:
        return JSONResponse({"error": "Chưa có file nào được upload"})
    try:
        answer = answer_question(uploaded_content, prompt)
        return JSONResponse({"response": answer})
    except Exception as e:
        return JSONResponse({"error": str(e)})
