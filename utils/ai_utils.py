import os
from openai import OpenAI

# Render lấy OPENAI_API_KEY trong Environment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_with_context(query: str, context: list[str]) -> str:
    context_text = "\n\n".join(context) if context else "No context available."

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # hoặc "gpt-4.1-mini"
        messages=[
            {"role": "system", "content": "You are an AI assistant that answers based on documents."},
            {"role": "user", "content": f"Question: {query}\n\nContext:\n{context_text}"}
        ],
    )
    return response.choices[0].message.content
