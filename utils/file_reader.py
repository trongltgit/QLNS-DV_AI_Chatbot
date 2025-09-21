from pypdf import PdfReader
from docx import Document

def read_file(file):
    ext = file.filename.split(".")[-1].lower()
    text = ""
    if ext == "pdf":
        reader = PdfReader(file.file)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    elif ext in ["docx", "doc"]:
        doc = Document(file.file)
        for para in doc.paragraphs:
            text += para.text + "\n"
    elif ext in ["txt", "csv"]:
        text = file.file.read().decode("utf-8")
    else:
        raise ValueError("Định dạng file không hỗ trợ")
    return text.strip()
