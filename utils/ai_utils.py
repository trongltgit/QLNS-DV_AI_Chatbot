import os
from openai import OpenAI

# Lấy API key từ biến môi trường
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_with_context(prompt: str, context: str = "") -> str:
    """
    Gọi OpenAI API với ngữ cảnh và prompt.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",   # nhẹ, nhanh, rẻ
        messages=[
            {"role": "system", "content": context},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()
