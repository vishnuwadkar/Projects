"""
ingest_vedabase.py — Vedabase-Aware Ingestion Pipeline
=======================================================
Loads scraped Vedabase JSON files, applies verse-aware chunking,
embeds each chunk using the Gemini Embedding API, and stores
everything in a local ChromaDB collection with rich metadata.

Key differences from generic ingest.py:
    - Verse-level chunking: each verse (translation + purport) is one chunk
    - Long purports are split with overlap, always including the translation
    - Rich metadata: book, chapter, verse, reference, URL for precise citations
    - Handles both verse-structured and prose-structured books

Usage:
    # Ingest all scraped books
    python ingest_vedabase.py

    # Ingest specific book(s)
    python ingest_vedabase.py --books bg sb

    # Re-ingest (clear existing data first)
    python ingest_vedabase.py --clear

Prerequisites:
    - Run scraper.py first to populate ./data/vedabase/
    - GEMINI_API_KEY set in .env
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path

# Fix Windows console encoding for Unicode/emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from google import genai
import chromadb


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path("./data/vedabase")
CHROMA_DIR = Path("./chroma_db")
COLLECTION_NAME = "vedabase_docs"
EMBEDDING_MODEL = "gemini-embedding-001"

# Chunking parameters
MAX_CHUNK_TOKENS = 800       # Max whitespace tokens per chunk
CHUNK_OVERLAP_TOKENS = 100   # Overlap for split purports
EMBED_BATCH_SIZE = 50        # Chunks per embedding API call


# ---------------------------------------------------------------------------
# Token Counting (whitespace-based approximation)
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Approximate token count using whitespace splitting."""
    return len(text.split())


# ---------------------------------------------------------------------------
# Verse-Aware Chunking
# ---------------------------------------------------------------------------

def chunk_verse_entry(entry: dict, book_code: str,
                      book_name: str) -> list[dict]:
    """
    Convert a single verse entry into one or more chunks with metadata.

    Strategy:
        - Combine translation + purport into a single searchable chunk
        - If the combined text exceeds MAX_CHUNK_TOKENS, split the purport
          into sub-chunks, each prefixed with the translation for context
        - Each chunk includes rich metadata for precise citation

    Returns a list of dicts with 'text' and 'metadata' keys.
    """
    translation = entry.get("translation", "").strip()
    purport = entry.get("purport", "").strip()
    synonyms = entry.get("synonyms", "").strip()
    reference = entry.get("reference", "Unknown")
    chapter = entry.get("chapter", "")
    chapter_title = entry.get("chapter_title", "")
    verse_number = entry.get("verse_number", "")
    url = entry.get("url", "")

    base_metadata = {
        "book": book_name,
        "book_code": book_code,
        "chapter": str(chapter),
        "chapter_title": chapter_title,
        "verse": str(verse_number),
        "reference": reference,
        "url": url,
    }

    chunks = []

    # Build the primary text: translation is always included
    header = f"[{reference}]\n"
    if translation:
        header += f"Translation: {translation}\n"

    # Case 1: Short enough for a single chunk
    combined = header
    if purport:
        combined += f"\nPurport: {purport}"

    if count_tokens(combined) <= MAX_CHUNK_TOKENS:
        content_type = "translation_and_purport" if purport else "translation"
        meta = {**base_metadata, "content_type": content_type, "chunk_index": 0}
        chunks.append({"text": combined, "metadata": meta})
    else:
        # Case 2: Purport is too long — split it
        # Always include translation as prefix in every sub-chunk
        purport_words = purport.split()
        purport_chunk_size = MAX_CHUNK_TOKENS - count_tokens(header) - 10
        purport_chunk_size = max(purport_chunk_size, 200)  # Safety floor

        start = 0
        chunk_idx = 0
        while start < len(purport_words):
            end = start + purport_chunk_size
            sub_purport = " ".join(purport_words[start:end])

            chunk_text = header + f"\nPurport (part {chunk_idx + 1}): {sub_purport}"
            meta = {
                **base_metadata,
                "content_type": "purport",
                "chunk_index": chunk_idx,
            }
            chunks.append({"text": chunk_text, "metadata": meta})

            start += purport_chunk_size - CHUNK_OVERLAP_TOKENS
            chunk_idx += 1

    # Optionally add synonyms as a separate searchable chunk
    if synonyms and count_tokens(synonyms) > 20:
        syn_text = f"[{reference}] — Word-by-word synonyms:\n{synonyms}"
        meta = {
            **base_metadata,
            "content_type": "synonyms",
            "chunk_index": 0,
        }
        chunks.append({"text": syn_text, "metadata": meta})

    return chunks


def chunk_prose_entry(entry: dict, book_code: str,
                      book_name: str) -> list[dict]:
    """
    Convert a prose/essay chapter entry into chunks.

    Uses fixed-size chunking with overlap, similar to the original ingest.py.
    """
    content = entry.get("content", "").strip()
    if not content:
        return []

    reference = entry.get("reference", "Unknown")
    chapter = entry.get("chapter", "")
    chapter_title = entry.get("chapter_title", "")
    url = entry.get("url", "")

    base_metadata = {
        "book": book_name,
        "book_code": book_code,
        "chapter": str(chapter),
        "chapter_title": chapter_title or reference,
        "verse": "",
        "reference": f"{book_name} — {reference}",
        "url": url,
        "content_type": "prose",
    }

    words = content.split()
    chunks = []

    if len(words) <= MAX_CHUNK_TOKENS:
        meta = {**base_metadata, "chunk_index": 0}
        header = f"[{base_metadata['reference']}]\n"
        chunks.append({"text": header + content, "metadata": meta})
    else:
        start = 0
        chunk_idx = 0
        while start < len(words):
            end = start + MAX_CHUNK_TOKENS
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)

            header = f"[{base_metadata['reference']}] (part {chunk_idx + 1})\n"
            meta = {**base_metadata, "chunk_index": chunk_idx}
            chunks.append({"text": header + chunk_text, "metadata": meta})

            start += MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS
            chunk_idx += 1

    return chunks


def chunk_special_page(entry: dict, book_code: str,
                       book_name: str) -> list[dict]:
    """Chunk special pages (preface, introduction, etc.)."""
    return chunk_prose_entry(entry, book_code, book_name)


# ---------------------------------------------------------------------------
# Load and Process Scraped Data
# ---------------------------------------------------------------------------

def load_and_chunk_book(json_path: Path) -> list[dict]:
    """
    Load a scraped book JSON file and produce all chunks.
    Returns a list of dicts with 'text' and 'metadata'.
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))
    book_code = data.get("book_code", json_path.stem)
    book_name = data.get("book", book_code)

    all_chunks = []

    # Process verses (verse-structured books)
    for entry in data.get("verses", []):
        chunks = chunk_verse_entry(entry, book_code, book_name)
        all_chunks.extend(chunks)

    # Process chapters (prose-structured books)
    for entry in data.get("chapters", []):
        chunks = chunk_prose_entry(entry, book_code, book_name)
        all_chunks.extend(chunks)

    # Process special pages (preface, intro, etc.)
    for entry in data.get("special_pages", []):
        chunks = chunk_special_page(entry, book_code, book_name)
        all_chunks.extend(chunks)

    return all_chunks


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_chunks(client: genai.Client, texts: list[str],
                 batch_size: int = EMBED_BATCH_SIZE) -> list:
    """
    Embed a list of text chunks using the Gemini Embedding API.
    Returns a list of embedding objects.
    """
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(texts) + batch_size - 1) // batch_size
        print(f"    Embedding batch {batch_num}/{total_batches} "
              f"({len(batch)} chunks)...")

        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config={
                "task_type": "RETRIEVAL_DOCUMENT",
            },
        )
        all_embeddings.extend(result.embeddings)

        # Rate-limit courtesy delay
        if i + batch_size < len(texts):
            time.sleep(1)

    return all_embeddings


# ---------------------------------------------------------------------------
# ChromaDB Storage
# ---------------------------------------------------------------------------

def store_in_chroma(chunks: list[dict], embeddings: list,
                    clear_existing: bool = False):
    """
    Upsert chunks + embeddings into the ChromaDB collection.
    Each chunk has rich metadata for precise citation.
    """
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if clear_existing:
        try:
            chroma_client.delete_collection(name=COLLECTION_NAME)
            print(f"  [OK] Cleared existing collection '{COLLECTION_NAME}'")
        except Exception:
            pass

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Build unique IDs
    ids = []
    documents = []
    metadatas = []
    embedding_values = []

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        # Create a unique, deterministic ID
        meta = chunk["metadata"]
        chunk_id = (
            f"{meta['book_code']}_"
            f"ch{meta['chapter']}_"
            f"v{meta['verse']}_"
            f"{meta['content_type']}_"
            f"{meta['chunk_index']}"
        )
        # Sanitize ID
        chunk_id = chunk_id.replace(" ", "_").replace("/", "_")

        ids.append(chunk_id)
        documents.append(chunk["text"])
        metadatas.append(meta)
        embedding_values.append(emb.values)

    # Upsert in batches (ChromaDB has batch limits)
    BATCH = 500
    for i in range(0, len(ids), BATCH):
        collection.upsert(
            ids=ids[i:i + BATCH],
            documents=documents[i:i + BATCH],
            embeddings=embedding_values[i:i + BATCH],
            metadatas=metadatas[i:i + BATCH],
        )

    print(f"  [OK] Stored {len(ids)} chunks in ChromaDB "
          f"(collection: '{COLLECTION_NAME}')")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ingest scraped Vedabase data into ChromaDB"
    )
    parser.add_argument(
        "--books", nargs="+", default=None,
        help="Specific book codes to ingest (default: all found in data/vedabase/)",
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear existing ChromaDB collection before ingesting",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("🕉️  Vedabase — Document Ingestion Pipeline")
    print("=" * 60)

    # Load API key
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n[X] GEMINI_API_KEY not found.")
        print("    Set it in your .env file or as an environment variable.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Find JSON files to ingest
    if not DATA_DIR.exists():
        print(f"\n[X] Data directory '{DATA_DIR}' not found.")
        print("    Run scraper.py first to download content from vedabase.io.")
        sys.exit(1)

    json_files = sorted(DATA_DIR.glob("*.json"))
    json_files = [f for f in json_files if f.name != "manifest.json"]

    if args.books:
        json_files = [f for f in json_files if f.stem in args.books]

    if not json_files:
        print("\n[X] No scraped JSON files found.")
        print("    Run scraper.py first to download content.")
        sys.exit(1)

    print(f"\n  Found {len(json_files)} book file(s) to ingest:")
    for f in json_files:
        print(f"    - {f.name}")

    # Process each book
    all_chunks = []
    for json_file in json_files:
        print(f"\n[LOAD] Processing {json_file.name} ...")
        chunks = load_and_chunk_book(json_file)
        all_chunks.extend(chunks)
        print(f"  → {len(chunks)} chunks generated")

    if not all_chunks:
        print("\n[X] No chunks generated. Check your scraped data.")
        sys.exit(1)

    print(f"\n  Total chunks across all books: {len(all_chunks)}")

    # Embed all chunks
    print(f"\n[EMBED] Generating embeddings via Gemini API...")
    texts = [c["text"] for c in all_chunks]
    embeddings = embed_chunks(client, texts)

    # Store in ChromaDB
    print(f"\n[STORE] Storing in ChromaDB...")
    store_in_chroma(all_chunks, embeddings, clear_existing=args.clear)

    # Summary
    print("\n" + "=" * 60)
    print("🕉️  Ingestion Complete!")
    print("=" * 60)

    # Count by book
    book_counts = {}
    for chunk in all_chunks:
        book = chunk["metadata"]["book"]
        book_counts[book] = book_counts.get(book, 0) + 1

    for book, count in book_counts.items():
        print(f"  📖 {book}: {count} chunks")

    print(f"\n  Total chunks  : {len(all_chunks)}")
    print(f"  Collection    : {COLLECTION_NAME}")
    print(f"  Storage       : {CHROMA_DIR.resolve()}")
    print(f"\n  Next step: streamlit run app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
