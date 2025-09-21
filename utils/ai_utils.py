import os
from openai import OpenAI

# Lấy API key từ biến môi trường Render
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_ai_response(prompt: str) -> str:
    """
    Hàm gọi OpenAI Chat Completions API để sinh câu trả lời.
    Trả về string.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",   # bạn có thể đổi sang gpt-4o hoặc gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "Bạn là chatbot AI hỗ trợ QLNS."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Lỗi khi gọi OpenAI API: {str(e)}"
