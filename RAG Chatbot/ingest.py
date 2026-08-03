"""
ingest.py — Document Ingestion Pipeline
========================================
Loads .txt/.md files from ./data, chunks them into ~500-token segments
with ~50-token overlap, embeds each chunk using the Gemini Embedding API,
and stores everything in a local ChromaDB collection.

Run once (or whenever your source documents change):
    python ingest.py

Prerequisites:
    - GEMINI_API_KEY set in .env or environment
    - pip install -r requirements.txt
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
import chromadb

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path("./data")                # Source documents directory
CHROMA_DIR = Path("./chroma_db")         # Persistent ChromaDB storage
COLLECTION_NAME = "rag_documents"        # ChromaDB collection name
EMBEDDING_MODEL = "gemini-embedding-001"   # Gemini embedding model
CHUNK_SIZE = 500                         # Target chunk size in whitespace tokens
CHUNK_OVERLAP = 50                       # Overlap between consecutive chunks
EMBED_BATCH_SIZE = 50                    # Chunks per embedding API call


# ---------------------------------------------------------------------------
# 1. Load Documents
# ---------------------------------------------------------------------------

def load_documents(data_dir: Path) -> list[dict]:
    """
    Read every .txt and .md file in `data_dir`.

    Returns a list of dicts:  [{"filename": "skills.txt", "content": "..."}]
    Skips empty files with a warning.
    """
    documents = []
    supported_extensions = {".txt", ".md"}

    for file_path in sorted(data_dir.iterdir()):
        if file_path.suffix.lower() not in supported_extensions:
            continue

        content = file_path.read_text(encoding="utf-8").strip()

        if not content:
            print(f"  [!] Skipping empty file: {file_path.name}")
            continue

        documents.append({
            "filename": file_path.name,
            "content": content,
        })
        print(f"  [OK] Loaded {file_path.name} ({len(content):,} chars)")

    return documents


# ---------------------------------------------------------------------------
# 2. Chunk Text
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split `text` into overlapping chunks of approximately `chunk_size`
    whitespace-delimited tokens, with `overlap` tokens shared between
    consecutive chunks.

    Why fixed-size chunking with overlap?
    - Simple and predictable — easy to reason about and tune.
    - Overlap ensures sentences split at a boundary still appear in at
      least one complete chunk, reducing information loss.
    - Whitespace tokenization is a fast, dependency-free approximation
      of LLM token counts (close enough for retrieval purposes).

    Returns a list of chunk strings.
    """
    words = text.split()  # Split on whitespace → list of "tokens"

    if len(words) <= chunk_size:
        # Document is small enough to be a single chunk
        return [text]

    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))

        # Advance by (chunk_size - overlap) to create the overlap region
        start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# 3. Embed Chunks
# ---------------------------------------------------------------------------

def embed_chunks(client: genai.Client, chunks: list[str],
                 batch_size: int = EMBED_BATCH_SIZE) -> list[list[float]]:
    """
    Embed a list of text chunks using the Gemini Embedding API.

    Chunks are sent in batches to minimize API calls and stay within
    free-tier rate limits. Each batch is a single API call that returns
    all embeddings at once.

    Returns a list of embedding vectors (list of floats).
    """
    all_embeddings = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        print(f"  Embedding batch {batch_num}/{total_batches} "
              f"({len(batch)} chunks)...")

        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config={
                "task_type": "RETRIEVAL_DOCUMENT",
            },
        )

        all_embeddings.extend(result.embeddings)

        # Small delay between batches to be kind to rate limits
        if i + batch_size < len(chunks):
            time.sleep(1)

    return all_embeddings


# ---------------------------------------------------------------------------
# 4. Store in ChromaDB
# ---------------------------------------------------------------------------

def store_in_chroma(chunks: list[str], embeddings: list,
                    metadatas: list[dict],
                    chroma_dir: Path = CHROMA_DIR,
                    collection_name: str = COLLECTION_NAME,
                    clear_existing: bool = False):
    """
    Upsert chunks + embeddings into a persistent ChromaDB collection.

    Each chunk is stored with:
      - its embedding vector
      - metadata: {"source": filename, "chunk_index": i}
      - a unique ID: "source__chunk_i"
    """
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    # Delete existing collection if re-ingesting fully
    if clear_existing:
        try:
            chroma_client.delete_collection(name=collection_name)
            print(f"  [OK] Cleared existing collection '{collection_name}'")
        except Exception:
            pass  # Collection didn't exist yet — that's fine

    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},  # Use cosine similarity
    )

    # Build unique IDs for each chunk
    ids = [
        f"{meta['source']}_chunk_{meta['chunk_index']}"
        for meta in metadatas
    ]

    # Extract raw embedding values
    embedding_values = [emb.values for emb in embeddings]

    # Upsert in one call (ChromaDB handles batching internally)
    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embedding_values,
        metadatas=metadatas,
    )

    print(f"  [OK] Stored {len(chunks)} chunks in ChromaDB "
          f"(collection: '{collection_name}')")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Run the full ingestion pipeline: load → chunk → embed → store."""
    print("=" * 60)
    print("RAG Chatbot — Document Ingestion")
    print("=" * 60)

    # --- Load environment & API key ---
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n[X] GEMINI_API_KEY not found.")
        print("    Set it in your .env file or as an environment variable.")
        print("    See .env.example for details.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # --- Step 1: Load documents ---
    print("\n[1/4] Loading documents from ./data ...")
    documents = load_documents(DATA_DIR)
    if not documents:
        print("\n[X] No documents found in ./data (or all files are empty).")
        print("    Add .txt or .md files to ./data and re-run.")
        sys.exit(1)

    # --- Step 2: Chunk documents ---
    print(f"\n[2/4] Chunking documents (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}) ...")
    all_chunks = []
    all_metadatas = []

    for doc in documents:
        chunks = chunk_text(doc["content"])
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({
                "source": doc["filename"],
                "chunk_index": i,
            })
        print(f"  [OK] {doc['filename']} -> {len(chunks)} chunk(s)")

    print(f"  Total: {len(all_chunks)} chunks across {len(documents)} files")

    # --- Step 3: Embed chunks ---
    print("\n[3] Generating Embeddings via Gemini API...")
    embeddings = embed_chunks(client, all_chunks)

    # --- Step 4: Store in ChromaDB ---
    print("\n[4] Storing in ChromaDB...")
    store_in_chroma(all_chunks, embeddings, all_metadatas, clear_existing=True)

    # --- Summary ---
    print("\n" + "=" * 60)
    print("Ingestion complete! You can now run `streamlit run app.py`")
    print("=" * 60)
    print(f"     Documents : {len(documents)}")
    print(f"     Chunks    : {len(all_chunks)}")
    print(f"     Storage   : {CHROMA_DIR.resolve()}")
    print(f"\n   Next step : streamlit run app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Dynamic UI Ingestion
# ---------------------------------------------------------------------------

def ingest_single_document(file_path: Path):
    """
    Ingest a single document dynamically from the UI.
    Appends to the existing ChromaDB collection.
    """
    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"File {file_path.name} is empty.")

    chunks_list = chunk_text(content)
    chunks = []
    metadatas = []
    for i, chunk in enumerate(chunks_list):
        chunks.append(chunk)
        metadatas.append({
            "source": file_path.name,
            "chunk_index": i,
        })
    
    if not chunks:
        raise ValueError("Could not extract any chunks from the document.")

    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment.")
        
    client = genai.Client(api_key=api_key)
    embeddings = embed_chunks(client, chunks)
    store_in_chroma(chunks, embeddings, metadatas, clear_existing=False)
