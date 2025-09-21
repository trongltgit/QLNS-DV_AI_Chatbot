from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import os

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
    # Giả lập tóm tắt file
    summary = f"Tệp {filename} đã được tải lên và tóm tắt sẽ ở đây."
    return JSONResponse({"filename": filename, "summary": summary})

# Chat endpoint
@app.post("/chat")
async def chat_endpoint(prompt: str = Form(...)):
    response_text = f"AI trả lời: {prompt}"  # Thay bằng logic AI thật
    return JSONResponse({"response": response_text})
