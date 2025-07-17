import os
import faiss
import numpy as np
from pypdf import PdfReader
import ollama
from config import PDF_FOLDER, EMBEDDING_MODEL, LLM_MODEL

# Load PDFs
def load_pdfs(folder_path):
    docs = []
    for file in os.listdir(folder_path):
        if file.endswith(".pdf"):
            pdf_path = os.path.join(folder_path, file)
            reader = PdfReader(pdf_path)
            text = "".join([page.extract_text() + "\n" for page in reader.pages])
            docs.append(text)
    return docs

# Split into chunks
def split_text(text, size=500):
    return [text[i:i+size] for i in range(0, len(text), size)]

# Get embedding from Ollama
def get_embedding(text):
    res = ollama.embeddings(model=EMBEDDING_MODEL, prompt=text)
    return np.array(res["embedding"], dtype="float32")

# Build FAISS index
def build_index(chunks):
    dim = len(get_embedding("test"))
    index = faiss.IndexFlatL2(dim)
    vectors, mapping = [], []
    for chunk in chunks:
        vectors.append(get_embedding(chunk))
        mapping.append(chunk)
    index.add(np.array(vectors))
    return index, mapping

# Query FAISS
def query_index(query, index, mapping, top_k=3):
    q_vec = get_embedding(query).reshape(1, -1)
    _, idx = index.search(q_vec, top_k)
    return [mapping[i] for i in idx[0]]

# Create knowledge base
docs = load_pdfs(PDF_FOLDER)
chunks = [chunk for doc in docs for chunk in split_text(doc)]
faiss_index, chunk_map = build_index(chunks)

# Main RAG query
def rag_query(user_query):
    context = "\n".join(query_index(user_query, faiss_index, chunk_map))
    prompt = f"Context:\n{context}\n\nQuestion: {user_query}\nAnswer:"
    response = ollama.chat(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}])
    return response["message"]["content"]
