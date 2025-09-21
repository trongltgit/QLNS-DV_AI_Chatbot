import os
from openai import OpenAI

# Khởi tạo client OpenAI với API key lấy từ biến môi trường
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_with_context(query: str, context: list[str]) -> str:
    """
    Tạo câu trả lời dựa trên câu hỏi (query) và ngữ cảnh (context).
    
    Args:
        query (str): Câu hỏi từ người dùng
        context (list[str]): Danh sách các đoạn văn bản trích xuất từ PDF
    
    Returns:
        str: Câu trả lời của AI
    """
    # Ghép context thành 1 đoạn văn
    context_text = "\n\n".join(context) if context else "Không có thông tin từ tài liệu."

    # Gửi request tới OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Hoặc gpt-4.1-mini (nhanh & rẻ hơn)
        messages=[
            {
                "role": "system",
                "content": "Bạn là trợ lý AI, giúp người dùng trả lời dựa trên tài liệu PDF họ đã upload."
            },
            {
                "role": "user",
                "content": f"Nội dung tài liệu:\n{context_text}\n\nCâu hỏi: {query}"
            }
        ],
        temperature=0.2,   # kiểm soát mức độ sáng tạo (0.0 = chặt chẽ, 1.0 = sáng tạo)
    )

    return response.choices[0].message.content.strip()
