from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader
from docx import Document
import os
import openai

# ----- Cấu hình -----
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# ----- Phục vụ static files -----
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

# ----- Lưu file và tóm tắt -----
uploaded_texts = {}  # key: filename, value: nội dung tóm tắt

def extract_text(file_path, filename):
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    elif filename.lower().endswith(".docx"):
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    elif filename.lower().endswith(".txt"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        return ""

def summarize_text(text):
    prompt = f"Tóm tắt ngắn gọn các điểm chính sau:\n\n{text}\n\nTóm tắt:"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return response.choices[0].message.content.strip()

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    text = extract_text(file_path, file.filename)
    if text:
        summary = summarize_text(text)
        uploaded_texts[file.filename] = text  # lưu nội dung gốc để chat
        return {"filename": file.filename, "summary": summary}
    else:
        return {"error": "Không thể đọc nội dung file."}

# ----- Chat với AI dựa trên file đã upload -----
@app.post("/chat")
async def chat_with_ai(prompt: str = Form(...), filename: str = Form(...)):
    if filename not in uploaded_texts:
        return {"error": "File chưa upload hoặc đã hết session."}

    context_text = uploaded_texts[filename]
    combined_prompt = f"Nội dung file:\n{context_text}\n\nHỏi: {prompt}\nTrả lời:"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": combined_prompt}],
            temperature=0.5
        )
        answer = response.choices[0].message.content.strip()
        return {"response": answer}
    except Exception as e:
        return {"error": str(e)}
