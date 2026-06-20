# app/rag.py

from openai import OpenAI                          # CHANGED
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_chroma import Chroma

from app.utils import CHROMA_COLLECTION, OPENAI_API_KEY, OPENAI_MODEL  # CHANGED
from app.prompts import build_prompt, NO_CONTEXT_RESPONSE
from app.ingest import CHROMA_PATH, EMBEDDING_MODEL

TOP_K     = 4
MIN_SCORE = 0.3

# Initialize the OpenAI client once at module level
# Why once? Creating a client per request wastes time and connections.
openai_client = OpenAI(api_key=OPENAI_API_KEY)    # CHANGED


def load_vector_store() -> Chroma:
    """Load ChromaDB — unchanged from Phase 4."""
    import os
    if not os.path.exists(CHROMA_PATH):
        raise FileNotFoundError(
            f"ChromaDB not found at '{CHROMA_PATH}'.\n"
            "Run ingestion first:  python3 -m app.ingest"
        )
    embedding_fn = SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)
    return Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=embedding_fn,
        persist_directory=CHROMA_PATH,
    )


def retrieve_chunks(question: str, vector_store: Chroma) -> list[dict]:
    """Retrieve relevant chunks — unchanged from Phase 4."""
    results = vector_store.similarity_search_with_relevance_scores(
        query=question,
        k=TOP_K,
    )
    chunks = []
    for doc, score in results:
        if score >= MIN_SCORE:
            chunks.append({
                "text":  doc.page_content,
                "url":   doc.metadata.get("url", "Unknown"),
                "score": round(score, 4),
            })
    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks


def generate_answer(prompt: str) -> str:
    """
    Send the grounded prompt to OpenAI and return the answer.

    What changed from Ollama version:
    - ollama.Client().chat()  →  openai_client.chat.completions.create()
    - options={temperature}   →  temperature= as a direct parameter
    - response["message"]["content"]  →  response.choices[0].message.content

    gpt-4o-mini is:
    - Faster than gemma3:4b for most queries
    - Better at following strict prompt instructions
    - ~$0.00015 per 1K input tokens — very cheap for Q&A
    - Requires internet (unlike Ollama)
    """
    response = openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                # System message sets behavior for the whole conversation.
                # We put our strict RAG rules here for extra enforcement.
                "role": "system",
                "content": (
                    "You are a precise support assistant. "
                    "Answer ONLY from the context provided. "
                    "Never use outside knowledge. "
                    "If context is insufficient, say so explicitly."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1,     # low = focused, factual answers
        max_tokens=512,      # enough for most support answers
    )
    return response.choices[0].message.content.strip()


def ask(question: str, vector_store: Chroma = None) -> dict:
    """Full RAG pipeline — unchanged from Phase 4."""
    if vector_store is None:
        vector_store = load_vector_store()

    print(f"\nSearching for: '{question}'")
    chunks = retrieve_chunks(question, vector_store)
    print(f"Found {len(chunks)} relevant chunks")

    if not chunks:
        return {
            "question":    question,
            "answer":      NO_CONTEXT_RESPONSE,
            "sources":     [],
            "chunks_used": 0,
        }

    prompt = build_prompt(question, chunks)
    print("Sending to OpenAI...")
    answer = generate_answer(prompt)

    sources = list(dict.fromkeys(c["url"] for c in chunks))
    return {
        "question":    question,
        "answer":      answer,
        "sources":     sources,
        "chunks_used": len(chunks),
    }


if __name__ == "__main__":
    store = load_vector_store()
    result = ask("What is a Python list?", vector_store=store)
    print(f"\nQ: {result['question']}")
    print(f"A: {result['answer']}")
    print(f"\nSources:")
    for url in result["sources"]:
        print(f"  - {url}")