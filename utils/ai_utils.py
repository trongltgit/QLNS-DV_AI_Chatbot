# utils/ai_utils.py
from openai import OpenAI

# Khởi tạo client - SDK sẽ tự động đọc OPENAI_API_KEY từ biến môi trường
client = OpenAI()

def chat_with_context(query: str, context_chunks: list[str], model: str = "gpt-4o-mini") -> str:
    """
    Trả lời câu hỏi dựa trên ngữ cảnh được cung cấp.

    Args:
        query (str): Câu hỏi từ người dùng.
        context_chunks (list[str]): Danh sách các đoạn text trích từ tài liệu.
        model (str): Model OpenAI sử dụng (mặc định: gpt-4o-mini).

    Returns:
        str: Câu trả lời từ AI.
    """
    # Ghép context thành một đoạn văn bản
    context_text = "\n\n".join(context_chunks)

    # Prompt
    prompt = f"""
Bạn là một trợ lý AI. Sử dụng NGỮ CẢNH bên dưới để trả lời câu hỏi.
Nếu thông tin không có trong ngữ cảnh, hãy nói rõ: "Không tìm thấy thông tin trong tài liệu".

NGỮ CẢNH:
{context_text}

CÂU HỎI:
{query}
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Bạn là một trợ lý AI hữu ích, chính xác và ngắn gọn."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Lỗi khi gọi OpenAI API: {e}"
