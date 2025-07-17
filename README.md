
# 🤖 Telegram Bot with Local LLM (Ollama) + RAG

This project is a **Telegram chatbot** that uses a **local LLM powered by Ollama** and a **Retrieval-Augmented Generation (RAG) pipeline** to answer user questions based on PDFs you provide.

---

## ✅ Features
- Full integration with **Telegram Bot API**
- **Local LLM inference** with Ollama (no cloud API needed)
- **RAG pipeline** for contextual answers from PDFs
- Handles **embeddings** using `mxbai-embed-large` (Ollama)
- Uses **FAISS** for vector search

---

## 🛠️ Requirements
- **Python**: 3.9+
- **Ollama** installed on your machine
- **Telegram Bot Token** (from [BotFather](https://t.me/BotFather))

---

## ⚙️ Step 1: Install Ollama
Download and install Ollama:
- [Download Ollama](https://ollama.ai/download)

Verify installation:
```bash
ollama --version
```

---

## ⚙️ Step 2-1: Pull the Models
### **Base LLM**
We will use `smollm:latest` (lightweight for local usage):
```bash
ollama pull smollm:latest
```

You can also try other models if your machine is powerful enough:
- `mistral`
- `llama2`
- `llama3`

Check installed models:
```bash
ollama list
```

---

### **Embedding Model**
We use `mxbai-embed-large` for embeddings:
```bash
ollama pull mxbai-embed-large
```

### **Run the LLM model**
Open a new terminal and execute:
```bash
ollama run your_llm_model #here it's smollm:latest
```

---

## ⚙️ Step 3: Clone the Project & Install Dependencies
```bash
git clone <your-repo-url>
cd telegram-bot
```

Create a virtual environment:
```bash
python -m venv .env
source .env/bin/activate      # On Linux/Mac
.env\Scripts\activate         # On Windows
```

Install dependencies:
```bash
pip install -r requirements.txt
```

---

## ⚙️ Step 4: Configure Environment Variables
Edit in the config.py file the following:
```env
TELEGRAM_BOT_TOKEN = your_bot_token
LLM_MODEL = your_model
```

Get your token from [BotFather](https://t.me/BotFather).

---

## ⚙️ Step 5: Add Your Documents for RAG
Place your **PDF files** in the folder called `data/`.

Example:
```
telegram-bot/
├── app.py
├── rag_pipeline.py
├── config.py
├── data/
    ├── file1.pdf
    ├── file2.pdf
```

The bot will **process these PDFs**, split them into chunks, embed them, and store them in FAISS for fast retrieval.

---

---

## ⚙️ Step 7: Run the Telegram Bot
Start the bot:
```bash
python app.py
```

You should see:
```
INFO:telegram.ext.Application:Application started
```

---

## ✅ How It Works
1. User sends a message in Telegram.
2. The bot retrieves **relevant chunks** from PDFs using FAISS.
3. It sends the query + retrieved context to **Ollama local model** (via HTTP).
4. The model generates an answer and sends it back to the user.

---

## 🔑 Commands
- `/start` → Starts the conversation
- `/help` → Displays help message
- Send any text → The bot will respond based on your PDFs and LLM

---

## ❗ Troubleshooting
- **Error: `model not found`** → Run:
  ```bash
  ollama pull smollm:latest
  ```
- **Port issues** → Ollama runs by default on `127.0.0.1:11434`
- **Windows tip**: Run `ollama` in a separate terminal before starting the bot

---

## ✅ Recommended Models
- `smollm:latest` → **Lightweight** (recommended for most PCs)
- `mistral` → Better reasoning, needs more RAM
- `llama3` → Heavy, needs 16GB+ RAM

---
