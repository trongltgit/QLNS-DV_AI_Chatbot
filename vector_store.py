import os
import faiss
import pickle
from sentence_transformers import SentenceTransformer

DB_DIR = "db"
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def _get_index_path(pdf_name):
    base = os.path.splitext(pdf_name)[0]
    return os.path.join(DB_DIR, f"{base}.faiss"), os.path.join(DB_DIR, f"{base}_chunks.pkl")

def build_faiss_index(chunks, pdf_name):
    embeddings = model.encode(chunks)
    d = embeddings.shape[1]
    index = faiss.IndexFlatL2(d)
    index.add(embeddings)

    index_path, chunk_path = _get_index_path(pdf_name)
    faiss.write_index(index, index_path)
    with open(chunk_path, "wb") as f:
        pickle.dump(chunks, f)

def search_faiss(query, top_k=3):
    all_indexes = [f for f in os.listdir(DB_DIR) if f.endswith(".faiss")]
    if not all_indexes:
        return ["Chưa có tài liệu nào."]

    all_results = []
    query_emb = model.encode([query])
    for idx_file in all_indexes:
        base = idx_file.replace(".faiss", "")
        index = faiss.read_index(os.path.join(DB_DIR, idx_file))
        with open(os.path.join(DB_DIR, f"{base}_chunks.pkl"), "rb") as f:
            chunks = pickle.load(f)

        D, I = index.search(query_emb, top_k)
        for i in I[0]:
            if i < len(chunks):
                all_results.append(chunks[i])

    return all_results[:top_k]
