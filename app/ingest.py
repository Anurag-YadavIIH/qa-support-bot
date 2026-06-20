# app/ingest.py
# Takes crawled pages, cleans text, splits into chunks,
# generates embeddings, and stores everything in ChromaDB.
# app/ingest.py — add at the very top
import os
os.environ["ANONYMIZED_TELEMETRY"] = "false"

import os
import re
import hashlib
from typing import List, Dict

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import SentenceTransformerEmbeddings as SentenceTransformerEmbeddings  # noqa
import warnings; warnings.filterwarnings("ignore", category=DeprecationWarning)
from langchain_chroma import Chroma

from app.utils import CHROMA_COLLECTION
from app.crawler import crawl


# ── Constants ──────────────────────────────────────────────────────────
# Path where ChromaDB will store its files on disk
CHROMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),  # project root
    "chroma_db"
)

# The local sentence-transformer model for embeddings
# "all-MiniLM-L6-v2" is small (~80MB), fast, and great for Q&A tasks
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Chunk settings — tune these if answers feel incomplete or too noisy
CHUNK_SIZE    = 500   # Max characters per chunk
CHUNK_OVERLAP = 100   # Characters shared between adjacent chunks


# ── Step 1: Text Cleaning ──────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Further clean raw crawled text before chunking.

    Why: Even after BeautifulSoup removes HTML tags, the text still has
    noise — excessive whitespace, unicode junk, repeated dashes, etc.
    Clean text → better embeddings → better search results.
    """
    # Replace Windows-style line endings with Unix
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove non-printable / control characters (except newlines and tabs)
    # \x00-\x08 and \x0b-\x1f are control characters we don't need
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)

    # Collapse 3+ consecutive newlines into just 2 (one blank line)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse multiple spaces into one
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Remove lines that are just punctuation or symbols (e.g. "------")
    text = re.sub(r"(?m)^[\W_]+$", "", text)

    # Remove encoding artifacts (e.g. Â¶ from mis-decoded UTF-8)
    text = text.encode("ascii", "ignore").decode("ascii")
    # Final strip
    return text.strip()


# ── Step 2: Chunking ───────────────────────────────────────────────────

def chunk_pages(pages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Split each crawled page into overlapping text chunks.

    Returns a list of chunk dicts:
    [
      {
        "text":    "The actual chunk text...",
        "url":     "https://source-page.com",
        "chunk_id": "abc123"   ← unique hash of the text
      },
      ...
    ]

    Why RecursiveCharacterTextSplitter?
    It tries to split on natural boundaries in this order:
      1. Paragraph breaks (\n\n)
      2. Line breaks (\n)
      3. Sentences (". ")
      4. Words (" ")
      5. Characters (last resort)
    This keeps chunks semantically coherent — sentences stay together
    whenever possible.
    """

    # Create the splitter with our settings
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        # These separators are tried in order — earlier = preferred
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,     # measure size in characters
    )

    all_chunks: List[Dict[str, str]] = []

    for page in pages:
        url  = page["url"]
        text = clean_text(page["text"])  # clean before splitting

        # Skip pages with very little content after cleaning
        if len(text) < 50:
            print(f"  ⚠️  Skipping near-empty page: {url}")
            continue

        # Split the page text into chunks
        # split_text() returns a plain list of strings
        raw_chunks = splitter.split_text(text)

        print(f"  📄 {url}")
        print(f"     → {len(raw_chunks)} chunks from {len(text)} chars")

        for chunk_text in raw_chunks:
            # Skip chunks that are too short to be useful
            if len(chunk_text.strip()) < 30:
                continue

            # Create a unique ID for this chunk using MD5 hash
            # Why hash? ChromaDB needs a unique ID per document.
            # Using the text itself as input means the same text
            # always gets the same ID — no duplicates on re-ingestion.
            chunk_id = hashlib.md5(
                (url + chunk_text + str(len(all_chunks))).encode("utf-8")
            ).hexdigest()

            all_chunks.append({
                "chunk_id": chunk_id,
                "text":     chunk_text.strip(),
                "url":      url,
            })

    print(f"\n✅ Total chunks created: {len(all_chunks)}")
    return all_chunks


# ── Step 3: Embeddings + ChromaDB Storage ─────────────────────────────

def get_embedding_function():
    """
    Load the sentence-transformer embedding model.

    What are embeddings?
    Embeddings convert text into a list of numbers (a "vector") that
    captures the *meaning* of the text. Similar meanings → similar
    numbers → close together in "vector space".

    Example:
      "Python lists are mutable"  → [0.12, -0.34, 0.89, ...]
      "Lists can be changed"      → [0.13, -0.31, 0.87, ...]  ← close!
      "The sky is blue"           → [-0.55, 0.22, -0.10, ...] ← far away

    all-MiniLM-L6-v2 produces 384-dimensional vectors.
    It runs entirely locally — no API calls, no cost.
    """
    return SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)


def ingest(pages: List[Dict[str, str]] = None) -> Chroma:
    """
    Full pipeline: crawl → clean → chunk → embed → store in ChromaDB.

    If pages is None, it will crawl the website first.
    Returns the Chroma vector store object (used later for retrieval).
    """

    # ── 1. Crawl if no pages provided ──
    if pages is None:
        print("🕷️  No pages provided — starting crawl first...\n")
        pages = crawl()

    # ── 2. Chunk all pages ──
    print("\n✂️  Chunking pages...")
    chunks = chunk_pages(pages)

    if not chunks:
        raise ValueError("No chunks created — check your crawled pages.")

    # ── 3. Load embedding model ──
    print("\n🧠 Loading embedding model (first run downloads ~80MB)...")
    embedding_fn = get_embedding_function()

    # ── 4. Prepare data for ChromaDB ──
    # ChromaDB expects three parallel lists:
    # - ids:       unique string ID per document
    # - documents: the actual text
    # - metadatas: dict of metadata per document (we store the URL)
    ids       = [c["chunk_id"] for c in chunks]
    documents = [c["text"]     for c in chunks]
    metadatas = [{"url": c["url"]} for c in chunks]

    # ── 5. Create / open ChromaDB collection ──
    print(f"\n💾 Storing {len(chunks)} chunks in ChromaDB...")
    print(f"   Path: {CHROMA_PATH}")
    print(f"   Collection: {CHROMA_COLLECTION}")

    # Chroma() creates a persistent database on disk at CHROMA_PATH.
    # If it already exists, it opens it.
    # collection_metadata={"hnsw:space": "cosine"} sets the similarity
    # metric to cosine similarity — standard for text embeddings.
    vector_store = Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        persist_directory=CHROMA_PATH,
        collection_metadata={"hnsw:space": "cosine"},
    )

    # add_texts() embeds each document and stores it with its metadata.
    # If an ID already exists, it's updated (not duplicated).
    vector_store.add_texts(
        texts=documents,
        metadatas=metadatas,
        ids=ids,
    )

    print(f"\n✅ Ingestion complete! {len(chunks)} chunks stored.")
    print(f"   ChromaDB saved to: {CHROMA_PATH}/")

    return vector_store


# ── Quick test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    store = ingest()

    # Quick sanity check — query the vector store directly
    print("\n🔍 Testing retrieval with a sample query...")
    results = store.similarity_search(
        "What is a Python list?",
        k=3  # return top 3 most similar chunks
    )

    print(f"\nTop {len(results)} results:\n")
    for i, doc in enumerate(results):
        print(f"--- Result {i+1} ---")
        print(f"URL:  {doc.metadata['url']}")
        print(f"Text: {doc.page_content[:200]}...")
        print()