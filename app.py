from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
import openai
import os

# ========================
# Cấu hình OpenAI API Key
# ========================
openai.api_key = os.getenv("OPENAI_API_KEY", "your-openai-key")

app = FastAPI(title="Render FastAPI Minimal Example")

# ========================
# Trang chủ / frontend
# ========================
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>FastAPI Render Demo</title>
        </head>
        <body>
            <h1>Upload & Chat Demo</h1>
            <form action="/upload" enctype="multipart/form-data" method="post">
                <input name="file" type="file">
                <input type="submit" value="Upload File">
            </form>
            <form action="/chat" method="post">
                <input name="prompt" type="text" placeholder="Ask AI">
                <input type="submit" value="Chat">
            </form>
        </body>
    </html>
    """

# ========================
# API Upload file
# ========================
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    content = await file.read()
    size = len(content)
    # Bạn có thể xử lý PDF / TXT / CSV ở đây
    return {"filename": file.filename, "size_bytes": size}

# ========================
# API Chat với OpenAI
# ========================
@app.post("/chat")
async def chat(prompt: str = Form(...)):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":prompt}],
            temperature=0.7
        )
        answer = response.choices[0].message.content
        return {"prompt": prompt, "answer": answer}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ========================
# Chạy local (dev)
# ========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
