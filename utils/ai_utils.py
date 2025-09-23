# utils/ai_utils.py
from openai import OpenAI
from utils import vector_store

client = OpenAI()

def summarize_text(text):
    prompt = f"Tóm tắt những điểm chính sau:\n\n{text[:2000]}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.3,
        max_tokens=300
    )
    return resp.choices[0].message.content.strip()

def answer_question(question):
    # lấy top 3 đoạn liên quan từ vector store
    context_chunks = vector_store.search_chunks(question, top_k=3)
    context = "\n".join(context_chunks) if context_chunks else "Không có tài liệu nào."
    
    prompt = (
        f"Bạn là AI trợ lý. Chỉ trả lời dựa trên tài liệu sau:\n\n{context}\n\n"
        f"Câu hỏi: {question}\n\n"
        f"Nếu không tìm thấy thông tin trong tài liệu, hãy trả lời: 'Không tìm thấy trong tài liệu.'"
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"system","content":"Bạn là trợ lý AI, chỉ trả lời dựa trên tài liệu được cung cấp."},
                  {"role":"user","content":prompt}],
        temperature=0.3,
        max_tokens=500
    )
    return resp.choices[0].message.content.strip()
