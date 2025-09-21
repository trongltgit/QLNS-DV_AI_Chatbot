import os
from openai import OpenAI

# Khởi tạo client - Render sẽ đọc OPENAI_API_KEY từ biến môi trường
client = OpenAI()

def chat_with_context(query, context):
    prompt = f"Bạn là trợ lý AI. Hãy trả lời dựa trên ngữ cảnh:\n\n{context}\n\nCâu hỏi: {query}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Hoặc "gpt-4o" nếu bạn có quyền
        messages=[
            {"role": "system", "content": "Bạn là trợ lý AI thông minh, trả lời ngắn gọn và rõ ràng."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content
