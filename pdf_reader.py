from pypdf import PdfReader

def extract_chunks(file_path, chunk_size=500):
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    return chunks
