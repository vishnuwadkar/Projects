# 🔍 RAG Chatbot Demo

A portfolio-ready **Retrieval-Augmented Generation (RAG)** chatbot that answers questions grounded exclusively in your documents, cites its sources, and explicitly refuses to answer when the context doesn't support it.

**Zero model training. Zero paid infrastructure. 100% free tier.**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Gemini](https://img.shields.io/badge/Gemini-2.5--flash-orange)
![ChromaDB](https://img.shields.io/badge/ChromaDB-local-green)
![Streamlit](https://img.shields.io/badge/Streamlit-chat--UI-red)

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Add your API key

```bash
cp .env.example .env
# Edit .env and paste your Gemini API key
# Get one free at: https://aistudio.google.com/apikey
```

### 3. Add your documents

Place `.txt` and/or `.md` files in the `./data` directory. These are the documents the chatbot will use to answer questions.

### 4. Run ingestion (once)

```bash
python ingest.py
```

This loads your documents, chunks them, embeds them using the Gemini Embedding API, and stores everything in a local ChromaDB database.

### 5. Launch the chatbot

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🏗️ Architecture

```
User Question
      │
      ▼
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│  Embed Query │───▶│  ChromaDB    │───▶│  Top-K=4     │
│  (text-      │    │  Cosine      │    │  Most Similar│
│  embedding-  │    │  Similarity  │    │  Chunks      │
│  004)        │    │  Search      │    │              │
└─────────────┘    └──────────────┘    └──────┬───────┘
                                              │
                                              ▼
                                    ┌──────────────────┐
                                    │  Build Prompt     │
                                    │  (Context + Query │
                                    │  + System Prompt) │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  Gemini 2.5 Flash │
                                    │  Generate Answer  │
                                    │  (grounded only)  │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                    ┌──────────────────┐
                                    │  Answer + Source  │
                                    │  Citations in UI  │
                                    └──────────────────┘
```

---

## 📁 Project Structure

```
rag-chatbot-demo/
├── data/                   # Your source documents (.txt, .md)
├── chroma_db/              # ChromaDB persistent storage (auto-created)
├── ingest.py               # Ingestion pipeline: load → chunk → embed → store
├── rag_pipeline.py         # Core RAG logic: retrieve → prompt → generate
├── app.py                  # Streamlit chat UI
├── requirements.txt        # Python dependencies
├── .env.example            # API key template
└── README.md               # This file
```

---

## 🎯 Design Decisions

### Chunking Strategy: Fixed-Size with Overlap

**What:** Documents are split into chunks of ~500 whitespace tokens with ~50 tokens of overlap between consecutive chunks.

**Why:**
- **Simple and predictable** — easy to reason about, tune, and explain
- **Overlap prevents information loss** — sentences split at chunk boundaries still appear in at least one complete chunk
- **Whitespace tokenization** is a fast, dependency-free approximation of LLM token counts (avoids adding a tokenizer dependency like `tiktoken`)
- **~500 tokens** is a sweet spot: large enough to contain meaningful context, small enough to fit multiple chunks in the LLM's context window

### Embedding Model: `gemini-embedding-001`

**Why this model:**
- **Free** — no credit card, no billing setup required
- **High quality** — 768-dimensional embeddings with strong retrieval performance
- **Task-type support** — `RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` for search queries (optimized for asymmetric retrieval)
- **No local compute** — runs as an API call, so the project works on any machine without GPU requirements

### Retrieval: Cosine Similarity, Top-K=4

**Why cosine similarity:** Standard for dense retrieval — measures directional similarity regardless of vector magnitude, which works well with normalized embeddings.

**Why K=4:** Provides enough context for multi-faceted questions without overwhelming the LLM's prompt. With ~500 tokens per chunk, 4 chunks ≈ 2,000 tokens of context — well within the model's window while leaving room for the answer.

### Generation: Strict Grounding Prompt

The system prompt explicitly instructs Gemini to:
1. Answer **only** from the provided context
2. Say "I don't have enough information" when the answer isn't in the context
3. Always cite source files

This minimizes hallucination — the model won't fabricate answers from its training data.

### Rate-Limit Handling

On a 429 (rate limit) error from the Gemini API:
1. Wait 5 seconds and retry once
2. If still rate-limited, show a friendly message (no crash, no traceback)

---

## 🔧 Customization

| Parameter | File | Default | Description |
|-----------|------|---------|-------------|
| `CHUNK_SIZE` | `ingest.py` | 500 | Target tokens per chunk |
| `CHUNK_OVERLAP` | `ingest.py` | 50 | Overlapping tokens between chunks |
| `TOP_K` | `rag_pipeline.py` | 4 | Number of chunks to retrieve |
| `GENERATION_MODEL` | `rag_pipeline.py` | `gemini-2.0-flash` | LLM for answer generation |
| `EMBEDDING_MODEL` | `ingest.py` | `gemini-embedding-001` | Embedding model |
| `temperature` | `rag_pipeline.py` | 0.2 | Generation temperature (lower = more factual) |

After changing ingestion parameters, re-run `python ingest.py`.

---

## 📋 Tech Stack

| Component | Technology | Cost |
|-----------|-----------|------|
| Embeddings | Google Gemini `gemini-embedding-001` | Free |
| LLM | Google Gemini `gemini-2.0-flash` | Free tier (1,500 req/day) |
| Vector Store | ChromaDB (local, persistent) | Free |
| UI | Streamlit | Free |
| Language | Python 3.11 | Free |
