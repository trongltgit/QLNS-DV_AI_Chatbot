import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

def ask_ai(question, docs):
    if not openai.api_key:
        return "Thiếu OPENAI_API_KEY."

    context = "\n\n".join(docs)
    prompt = f"Bạn là một chatbot. Dựa trên tài liệu sau, trả lời ngắn gọn:\n\n{context}\n\nCâu hỏi: {question}"

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Bạn là trợ lý AI hữu ích."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message["content"]
    except Exception as e:
        return f"Lỗi AI: {e}"
