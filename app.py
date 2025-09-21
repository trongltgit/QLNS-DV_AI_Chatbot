import os
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pypdf import PdfReader
import docx
import pandas as pd
import openai

# --- Cấu hình ---
openai.api_key = os.getenv("OPENAI_API_KEY")  # Set trên Render
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- FastAPI app ---
app = FastAPI()

# Cho phép frontend truy cập
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Lưu nội dung file đã upload vào memory ---
memory_docs = []

# ------------------ Utils ------------------
def read_txt(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def read_pdf(file_path):
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def read_docx(file_path):
    doc = docx.Document(file_path)
    text = "\n".join([p.text for p in doc.paragraphs])
    return text

def read_xlsx(file_path):
    df = pd.read_excel(file_path, engine="xlrd")
    return df.to_string(index=False)

def extract_file_content(file_path):
    ext = file_path.split(".")[-1].lower()
    if ext == "txt":
        return read_txt(file_path)
    elif ext == "pdf":
        return read_pdf(file_path)
    elif ext == "docx":
        return read_docx(file_path)
    elif ext in ["xls", "xlsx"]:
        return read_xlsx(file_path)
    else:
        return ""

# ------------------ Routes ------------------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        save_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # đọc nội dung và lưu vào memory
        text_content = extract_file_content(save_path)
        memory_docs.append(text_content)

        return {"filename": file.filename, "size": len(content)}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/chat")
async def chat_with_ai(prompt: str = Form(...), max_tokens: int = 500):
    try:
        # Ghép toàn bộ file đã upload
        context = "\n\n".join(memory_docs) or "No uploaded document."
        system_prompt = (
            "Bạn là trợ lý AI giúp tóm tắt nội dung văn bản. "
            "Dựa trên nội dung đã upload, trả lời câu hỏi của người dùng."
        )
        user_prompt = f"{context}\n\nNgười dùng hỏi: {prompt}\nTrả lời tóm tắt:"

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.5
        )

        answer = response.choices[0].message.content.strip()
        return {"response": answer}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
