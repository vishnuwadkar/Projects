# 🕉️ Vedabase Spiritual AI Chatbot

A specialized, high-precision **Retrieval-Augmented Generation (RAG)** chatbot designed to answer complex spiritual queries grounded strictly in **A.C. Bhaktivedanta Swami Prabhupāda's** translation and purports from **[vedabase.io](https://vedabase.io)** (Bhagavad-gītā As It Is, Śrīmad-Bhāgavatam, Śrī Caitanya-caritāmṛta, etc.).

> **Zero Hallucination Guarantee:** The system uses strict prompt-grounding and explicit source verification. If a query is not directly answered by authentic Vedic texts in the database, it clearly states the boundary of available knowledge without inventing self-made theories.

---

## ✨ Features

- 📜 **Verse-Aware Chunking**: Intelligently groups Devanagari, Sanskrit transliteration, word-for-word synonyms, translation, and purports into holistic semantic chunks.
- 🔗 **Direct Scripture Citations & Deep-Links**: Every generated answer includes clickable references to exact verses (e.g. *Bhagavad-gītā 2.13*) pointing directly to `vedabase.io`.
- 🪔 **Spiritual & Reverent Aesthetics**: Premium dark/light themes featuring saffron (`#D97706`) and deep maroon (`#991B1B`) visual hierarchy with elegant serif typography.
- ⚡ **Streamlined Scraper & Checkpointer**: Includes an asynchronous Playwright crawler with strict `robots.txt` compliance (10s delay) and state resume capabilities.
- 🧠 **Gemini 2.5 & ChromaDB Vector Store**: Fast semantic search using `gemini-embedding-001` and generation powered by `gemini-2.5-flash`.

---

## 🚀 Quick Start

### 1. Install Dependencies & Browser Runtimes

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

*(Get a free API key at [Google AI Studio](https://aistudio.google.com/apikey))*

---

## 📥 Scraping & Ingestion Pipeline

### Step 1: Scrape Vedabase Content

Use `scraper.py` to extract content directly from `vedabase.io`:

```bash
# Scrape Bhagavad-gītā As It Is (Recommended first test)
python scraper.py --books bg

# Scrape multiple major texts (e.g. Bhagavad-gītā & Śrīmad-Bhāgavatam)
python scraper.py --books bg sb

# Resume an interrupted scrape session
python scraper.py --books bg --resume
```

Scraped entries are stored as structured JSON files under `./data/vedabase/<book_code>/`.

### Step 2: Verse-Aware Vector Storage

Ingest the scraped JSON files into the vector database (`chroma_db`):

```bash
# Ingest all scraped books
python ingest_vedabase.py

# Ingest specific book(s)
python ingest_vedabase.py --books bg

# Clear database and re-ingest
python ingest_vedabase.py --clear
```

---

## 💬 Launching the Chatbot UI

Start the Streamlit application:

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your web browser.

---

## 🏗️ System Architecture

```
                 ┌───────────────────────────┐
                 │    vedabase.io Scraper    │
                 │   (Playwright + Async)    │
                 └─────────────┬─────────────┘
                               │ Structured JSON
                               ▼
                 ┌───────────────────────────┐
                 │   ingest_vedabase.py      │
                 │   Verse-Aware Chunking    │
                 └─────────────┬─────────────┘
                               │ Chunks + Metadata
                               ▼
┌──────────────┐ ┌───────────────────────────┐
│ User Query   │ │   Gemini Embedding API    │
└──────┬───────┘ └─────────────┬─────────────┘
       │                       │ Embeddings
       ▼                       ▼
┌────────────────────────────────────────────┐
│      ChromaDB Vector Store (Collection)    │
└──────────────────────┬─────────────────────┘
                       │ Top-K Relevant Chunks
                       ▼
┌────────────────────────────────────────────┐
│      Spiritual Prompt Grounding Engine     │
│   Strict Prabhupāda Teachings Alignment   │
└──────────────────────┬─────────────────────┘
                       │ Grounded Context
                       ▼
┌────────────────────────────────────────────┐
│          Gemini 2.5 Flash Model            │
└──────────────────────┬─────────────────────┘
                       │ Streamed Response
                       ▼
┌────────────────────────────────────────────┐
│   Streamlit UI (Citations + Deep Links)   │
└────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
RAG Chatbot/
├── data/
│   └── vedabase/         # Scraped book JSON files and crawler manifest
├── chroma_db/            # Local ChromaDB persistent vector database
├── scraper.py            # Playwright crawler with robots.txt compliance & resume capability
├── ingest_vedabase.py    # Verse-aware chunking and embedding storage pipeline
├── ingest.py             # Legacy document ingestion pipeline (fallback for txt/pdf)
├── rag_pipeline.py       # Core RAG engine with spiritual grounding and prompt rules
├── app.py                # Spiritually-themed Streamlit chat interface
├── requirements.txt      # Python dependencies
└── README.md             # Project documentation
```
