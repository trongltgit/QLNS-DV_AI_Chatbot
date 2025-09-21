from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from openai import OpenAI
import os

# Khởi tạo client với API key từ biến môi trường RENDER
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# Mount thư mục static (CSS, JS, hình ảnh,...)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Template folder
templates = Jinja2Templates(directory="templates")

# Trang chủ
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Upload file
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename
    save_path = f"static/{filename}"
    with open(save_path, "wb") as f:
        f.write(await file.read())

    # Tóm tắt file bằng GPT
    try:
        with open(save_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[:2000]  # chỉ lấy 2000 ký tự đầu để không quá dài
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

# Chat endpoint
@app.post("/chat")
async def chat_endpoint(prompt: str = Form(...)):
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là AI trợ lý thông minh, luôn trả lời rõ ràng."},
                {"role": "user", "content": prompt}
            ]
        )
        response_text = completion.choices[0].message.content
    except Exception as e:
        response_text = f"AI API error: {e}"

    return JSONResponse({"response": response_text})
