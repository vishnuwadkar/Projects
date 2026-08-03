"""
rag_pipeline.py  --  Retrieval-Augmented Generation Pipeline
==========================================================
Core RAG logic: embed a user query, retrieve relevant chunks from ChromaDB,
build a grounded prompt, and generate an answer using Gemini.

This module is imported by app.py (Streamlit UI). It can also be used
standalone for testing:

    from rag_pipeline import query_rag
    result = query_rag("What are Vishnu's skills?")
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
COLLECTION_NAME = "rag_documents"
EMBEDDING_MODEL = "gemini-embedding-001"
GENERATION_MODEL = "gemini-flash-latest"
TOP_K = 4          # Number of chunks to retrieve
RETRY_DELAY = 5    # Seconds to wait before retrying on rate limit

# Strict system prompt to minimize hallucination
SYSTEM_PROMPT = """You are a helpful assistant. Answer the user's question ONLY using the provided context below. Follow these rules strictly:

1. Use ONLY the information in the CONTEXT to answer. Do NOT use any outside knowledge.
2. If the answer is not contained in the context, respond with: "I don't have enough information in the provided documents to answer that question."
3. At the end of your answer, always list which source file(s) you used in a "Sources:" section.
4. Be concise and direct in your answers.
5. If the context partially answers the question, answer what you can and note what information is missing."""


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
    Returns the collection object, or raises if ingestion hasn't run.
    """
    global _chroma_collection
    if _chroma_collection is None:
        if not CHROMA_DIR.exists():
            raise FileNotFoundError(
                f"ChromaDB directory '{CHROMA_DIR}' not found. "
                "Run 'python ingest.py' first to ingest your documents."
            )
        chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _chroma_collection = chroma_client.get_collection(
            name=COLLECTION_NAME,
        )
    return _chroma_collection


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve_chunks(query: str, top_k: int = TOP_K) -> dict:
    """
    Embed the user query and retrieve the top-k most similar chunks
    from ChromaDB using cosine similarity.

    Returns a dict with:
      - "documents": list of chunk texts
      - "metadatas": list of metadata dicts (source, chunk_index)
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

    Each chunk is numbered and labeled with its source file so the LLM
    can cite specific sources in its answer.
    """
    context_parts = []
    for i, (doc, meta) in enumerate(
        zip(retrieved["documents"], retrieved["metadatas"]), start=1
    ):
        source = meta["source"]
        chunk_idx = meta["chunk_index"]
        context_parts.append(
            f"[Chunk {i}] (Source: {source}, Chunk #{chunk_idx})\n{doc}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    prompt = f"""CONTEXT:
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
    the generated answer.

    Rate-limit handling:
      - On a 429 error, extract the retry delay from the API response
        (or use exponential backoff) and retry up to 3 times.
      - If all retries fail, return a friendly error message.
    """
    client = _get_genai_client()
    prompt = build_prompt(query, retrieved)
    max_retries = 3
    base_delay = RETRY_DELAY  # 5 seconds

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GENERATION_MODEL,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.2,  # Low temp for factual grounding
                },
            )
            return response.text

        except genai_errors.ClientError as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

            if is_rate_limit and attempt < max_retries - 1:
                # Try to extract suggested retry delay from error message
                import re
                delay_match = re.search(r"retry in ([\d.]+)s", error_str)
                if delay_match:
                    wait_time = min(float(delay_match.group(1)) + 1, 60)
                else:
                    # Exponential backoff: 10s, 20s, 30s
                    wait_time = base_delay * (attempt + 2)
                time.sleep(wait_time)
                continue
            elif is_rate_limit:
                # All retries exhausted -- give up gracefully
                return (
                    "The Gemini API is currently rate-limited. "
                    "Please wait about 30 seconds and try again. "
                    "(Free tier has per-minute quotas)"
                )
            else:
                # Non-rate-limit error -- re-raise
                raise


# ---------------------------------------------------------------------------
# Streaming Generation (for real-time UI feedback)
# ---------------------------------------------------------------------------

def generate_answer_stream(query: str, retrieved: dict):
    """
    Stream the generated answer token-by-token for real-time UI display.

    Yields text chunks as they arrive from Gemini, making the response
    feel much faster even though total time is similar.

    Falls back to non-streaming on rate-limit errors.
    """
    client = _get_genai_client()
    prompt = build_prompt(query, retrieved)
    max_retries = 3
    base_delay = RETRY_DELAY

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content_stream(
                model=GENERATION_MODEL,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.2,
                },
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return  # Done streaming

        except genai_errors.ClientError as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

            if is_rate_limit and attempt < max_retries - 1:
                import re
                delay_match = re.search(r"retry in ([\d.]+)s", error_str)
                if delay_match:
                    wait_time = min(float(delay_match.group(1)) + 1, 60)
                else:
                    wait_time = base_delay * (attempt + 2)
                time.sleep(wait_time)
                continue
            elif is_rate_limit:
                yield (
                    "The Gemini API is currently rate-limited. "
                    "Please wait about 30 seconds and try again. "
                    "(Free tier has per-minute quotas)"
                )
                return
            else:
                raise


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
    for doc, meta, dist in zip(
        retrieved["documents"],
        retrieved["metadatas"],
        retrieved["distances"],
    ):
        sources.append({
            "text": doc,
            "source": meta["source"],
            "chunk_index": meta["chunk_index"],
            "distance": round(dist, 4),
        })
    return sources

