from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from utils.ai_utils import generate_ai_response
from pydantic import BaseModel

app = FastAPI()

# cấu hình templates
templates = Jinja2Templates(directory="templates")

class ChatRequest(BaseModel):
    prompt: str

# Route trang chủ -> render index.html
@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# API chat
@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        response_text = await generate_ai_response(request.prompt)
        return {"response": response_text}
    except Exception as e:
        return {"error": str(e)}
