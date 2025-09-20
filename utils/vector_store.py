# Vector store đơn giản bằng list trong RAM
stored_chunks = []

def store_chunks(chunks):
    global stored_chunks
    stored_chunks.extend(chunks)

def search_chunks(query, top_k=3):
    # tìm text gần giống (match substring)
    results = [c for c in stored_chunks if query.lower() in c.lower()]
    return results[:top_k] if results else stored_chunks[:top_k]
