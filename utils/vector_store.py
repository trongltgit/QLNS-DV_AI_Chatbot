# utils/vector_store.py
from openai import OpenAI
import numpy as np

client = OpenAI()

stored_chunks = []
stored_vectors = []

def embed_text(text):
    """Tạo embedding cho 1 đoạn văn bản"""
    emb = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return np.array(emb.data[0].embedding, dtype="float32")

def store_chunks(chunks):
    """Lưu chunk và embedding vào RAM"""
    global stored_chunks, stored_vectors
    for c in chunks:
        stored_chunks.append(c)
        stored_vectors.append(embed_text(c))

def search_chunks(query, top_k=3):
    """Tìm top_k đoạn liên quan nhất với query"""
    if not stored_chunks:
        return []

    q_vec = embed_text(query)
    sims = [np.dot(q_vec, v) / (np.linalg.norm(q_vec) * np.linalg.norm(v)) for v in stored_vectors]
    ranked = sorted(zip(sims, stored_chunks), key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:top_k]]
