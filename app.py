from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from openai import OpenAI
import os

# Khởi tạo client với OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# ===== CORS Middleware =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # cho phép tất cả domain (có thể giới hạn sau này)
    allow_credentials=True,
    allow_methods=["*"],   # cho phép tất cả phương thức (GET, POST,...)
    allow_headers=["*"],   # cho phép tất cả headers
)

# Mount static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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
        with open(save_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[:2000]
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là AI chuyên tóm tắt văn bản ngắn gọn."},
                {"role": "user", "content": f"Hãy tóm tắt nội dung sau:\n{content}"}
            ]
        )
        summary = completion.choices[0].message.content
    except Exception as e:
        summary = f"Không thể tóm tắt file: {e}"

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
        response_text = f"AI API error: {e}"

    return JSONResponse({"response": response_text})
