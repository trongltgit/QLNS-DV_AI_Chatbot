import openai

openai.api_key = "YOUR_OPENAI_KEY"

def summarize_text(text):
    prompt = f"Tóm tắt những điểm chính sau:\n\n{text[:2000]}"
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.3,
        max_tokens=300
    )
    return resp['choices'][0]['message']['content'].strip()

def answer_question(text, question):
    prompt = (
        f"Bạn là AI trợ lý. Dựa trên nội dung sau:\n\n{text[:2000]}\n\n"
        f"Trả lời câu hỏi sau một cách chi tiết:\n{question}"
    )
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.3,
        max_tokens=500
    )
    return resp['choices'][0]['message']['content'].strip()
