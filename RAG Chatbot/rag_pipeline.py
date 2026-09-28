"""
rag_pipeline.py  --  Vedabase Spiritual RAG Pipeline
=====================================================
Core RAG logic: embed a user query, retrieve relevant chunks from ChromaDB,
build a grounded spiritual prompt, and generate an answer using Gemini.

This module is imported by app.py (Streamlit UI). It can also be used
standalone for testing:

    from rag_pipeline import query_rag
    result = query_rag("What does Krishna say about the soul?")
    print(result["answer"])
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
import chromadb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHROMA_DIR = Path("./chroma_db")
COLLECTION_NAME = "vedabase_docs"
EMBEDDING_MODEL = "gemini-embedding-001"

GENERATION_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]

TOP_K = 4  # Optimized for faster responses while retaining high precision
RETRY_DELAY = 3  # Reduced retry delay


# Strict spiritual grounding prompt
SYSTEM_PROMPT = """You are a scholarly spiritual assistant grounded exclusively in the teachings of His Divine Grace A.C. Bhaktivedanta Swami Prabhupāda, as published on vedabase.io.

You have access to the translations and purports of sacred Vedic texts including Bhagavad-gītā As It Is, Śrīmad-Bhāgavatam, Śrī Caitanya-caritāmṛta, and other books by Śrīla Prabhupāda.

RULES — follow these strictly:

1. Answer ONLY from the provided CONTEXT. Never use outside knowledge or your own training data.
2. When quoting a verse translation, format it as a blockquote and cite the reference (e.g., BG 2.47).
3. When explaining a concept, reference the purport and cite the source precisely.
4. If the context does not contain the answer, respond with:
   "I could not find a direct reference in the available scriptures for this question. You may want to search vedabase.io directly for more information."
5. Always include a "📖 Sources" section at the end listing each scripture reference used, formatted as:
   - **Reference** — Book Name (Chapter Title)
6. Be respectful of the Vaiṣṇava tradition. Use proper diacritical marks for Sanskrit terms where possible.
7. Do NOT speculate, interpret beyond what Śrīla Prabhupāda has written, or mix in teachings from other spiritual traditions.
8. Be concise but thorough. If multiple verses are relevant, cite all of them.
9. If the context only partially answers the question, answer what you can and note what additional information might be found.
10. When asked about practices (chanting, meditation, devotion), ground your answer in the specific instructions from the purports."""


# ---------------------------------------------------------------------------
# Initialize clients (lazy, cached)
# ---------------------------------------------------------------------------

_genai_client = None
_chroma_collection = None


def _get_genai_client() -> genai.Client:
    """
    Return a cached Gemini API client.
    Loads the API key from .env or environment on first call.
    """
    global _genai_client
    if _genai_client is None:
        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not found. "
                "Set it in your .env file or as an environment variable."
            )
        _genai_client = genai.Client(api_key=api_key)
    return _genai_client


def get_chroma_collection():
    """
    Connect to the persisted ChromaDB collection.
    Returns the collection object, falling back to 'rag_documents' or creating 'vedabase_docs'
    if ingestion hasn't been run yet.
    """
    global _chroma_collection
    if _chroma_collection is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        
        try:
            _chroma_collection = chroma_client.get_collection(name=COLLECTION_NAME)
        except Exception:
            # Check if legacy collection exists
            existing = [c.name for c in chroma_client.list_collections()]
            if "rag_documents" in existing:
                _chroma_collection = chroma_client.get_collection(name="rag_documents")
            else:
                _chroma_collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)
    return _chroma_collection



def get_collection_stats() -> dict:
    """Return stats about the ChromaDB collection for the UI."""
    try:
        collection = get_chroma_collection()
        count = collection.count()

        # Sample some metadata to get book list
        sample = collection.peek(limit=100)
        books = set()
        for meta in sample.get("metadatas", []):
            if meta and "book" in meta:
                books.add(meta["book"])

        return {
            "total_chunks": count,
            "books": sorted(books),
            "collection_name": COLLECTION_NAME,
        }
    except Exception:
        return {"total_chunks": 0, "books": [], "collection_name": COLLECTION_NAME}


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve_chunks(query: str, top_k: int = TOP_K) -> dict:
    """
    Embed the user query and retrieve the top-k most similar chunks
    from ChromaDB using cosine similarity.

    Returns a dict with:
      - "documents": list of chunk texts
      - "metadatas": list of metadata dicts (book, chapter, verse, etc.)
      - "distances": list of cosine distances (lower = more similar)
    """
    client = _get_genai_client()

    # Embed the query using the same model as ingestion,
    # but with RETRIEVAL_QUERY task type for optimal retrieval
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[query],
        config={
            "task_type": "RETRIEVAL_QUERY",
        },
    )
    query_embedding = result.embeddings[0].values

    # Query ChromaDB for the most similar chunks
    collection = get_chroma_collection()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    return {
        "documents": results["documents"][0],
        "metadatas": results["metadatas"][0],
        "distances": results["distances"][0],
    }


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

def build_prompt(query: str, retrieved: dict) -> str:
    """
    Assemble the user prompt with retrieved context chunks.

    Each chunk is labeled with its scripture reference so the LLM
    can cite specific sources in its answer.
    """
    context_parts = []
    for i, (doc, meta) in enumerate(
        zip(retrieved["documents"], retrieved["metadatas"]), start=1
    ):
        reference = meta.get("reference", "Unknown")
        book = meta.get("book", "")
        chapter_title = meta.get("chapter_title", "")
        content_type = meta.get("content_type", "")

        label = f"[Source {i}] {reference}"
        if chapter_title:
            label += f" — {chapter_title}"

        context_parts.append(f"### {label}\n{doc}")

    context_block = "\n\n---\n\n".join(context_parts)

    prompt = f"""CONTEXT (from Vedabase scriptures):
{context_block}

USER QUESTION:
{query}"""

    return prompt


# ---------------------------------------------------------------------------
# Generation (with rate-limit retry)
# ---------------------------------------------------------------------------

def generate_answer(query: str, retrieved: dict) -> str:
    """
    Send the retrieved context + user question to Gemini and return
    the generated answer, automatically falling back across model candidates.
    """
    client = _get_genai_client()
    prompt = build_prompt(query, retrieved)

    last_exception = None
    for model in GENERATION_MODELS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "system_instruction": SYSTEM_PROMPT,
                        "temperature": 0.2,
                    },
                )
                return response.text
            except genai_errors.ClientError as e:
                error_str = str(e)
                last_exception = e
                if "404" in error_str or "NOT_FOUND" in error_str:
                    # Model not available in this region/key tier -- try next candidate
                    break
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                break
    
    if last_exception:
        raise last_exception
    return "Unable to generate answer."


def generate_answer_stream(query: str, retrieved: dict):
    """
    Stream the generated answer token-by-token for real-time UI display,
    falling back to candidate models if a model is unavailable.
    """
    client = _get_genai_client()
    prompt = build_prompt(query, retrieved)

    last_exception = None
    for model in GENERATION_MODELS:
        try:
            response = client.models.generate_content_stream(
                model=model,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.2,
                },
            )
            has_yielded = False
            for chunk in response:
                if chunk.text:
                    has_yielded = True
                    yield chunk.text
            if has_yielded:
                return
        except genai_errors.ClientError as e:
            error_str = str(e)
            last_exception = e
            if "404" in error_str or "NOT_FOUND" in error_str:
                continue
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                time.sleep(RETRY_DELAY)
                continue
            raise e

    if last_exception:
        yield f"🙏 Error accessing Gemini model: {last_exception}"



# ---------------------------------------------------------------------------
# Top-level convenience functions
# ---------------------------------------------------------------------------

def query_rag(user_question: str) -> dict:
    """
    Full RAG pipeline: retrieve relevant chunks -> generate grounded answer.

    Returns a dict with:
      - "answer": the generated response string
      - "sources": list of dicts with source info for each retrieved chunk
    """
    # Step 1: Retrieve relevant chunks
    retrieved = retrieve_chunks(user_question)

    # Step 2: Generate answer using retrieved context
    answer = generate_answer(user_question, retrieved)

    # Step 3: Package source information for the UI
    sources = _package_sources(retrieved)

    return {
        "answer": answer,
        "sources": sources,
    }


def query_rag_stream(user_question: str) -> dict:
    """
    Streaming RAG pipeline: retrieve chunks, then stream the answer.

    Returns a dict with:
      - "stream": a generator yielding answer text chunks
      - "sources": list of dicts with source info (available immediately)
    """
    # Step 1: Retrieve relevant chunks (fast, local ChromaDB lookup)
    retrieved = retrieve_chunks(user_question)

    # Step 2: Package sources immediately so the UI can show them
    sources = _package_sources(retrieved)

    # Step 3: Return the stream generator (answer streams in real-time)
    return {
        "stream": generate_answer_stream(user_question, retrieved),
        "sources": sources,
    }


def _package_sources(retrieved: dict) -> list[dict]:
    """Extract source metadata from retrieved chunks for the UI."""
    sources = []
    seen_refs = set()

    for doc, meta, dist in zip(
        retrieved["documents"],
        retrieved["metadatas"],
        retrieved["distances"],
    ):
        reference = meta.get("reference", "Unknown")

        # Deduplicate by reference (same verse may appear in multiple chunks)
        if reference in seen_refs:
            continue
        seen_refs.add(reference)

        sources.append({
            "text": doc,
            "reference": reference,
            "book": meta.get("book", ""),
            "book_code": meta.get("book_code", ""),
            "chapter": meta.get("chapter", ""),
            "chapter_title": meta.get("chapter_title", ""),
            "verse": meta.get("verse", ""),
            "content_type": meta.get("content_type", ""),
            "url": meta.get("url", ""),
            "similarity": round(1 - dist, 4),  # Convert distance to similarity
        })
    return sources
