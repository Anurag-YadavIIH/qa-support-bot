# app/main.py
# FastAPI application — the HTTP interface for the RAG bot.
#
# Endpoints:
#   GET  /          → health check
#   GET  /status    → check if ChromaDB is ready
#   POST /ask       → ask a question, get an answer
#   POST /ingest    → trigger re-crawl + re-ingestion

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.rag import ask, load_vector_store
from app.ingest import ingest


# ── Shared state ───────────────────────────────────────────────────────
# We load the vector store ONCE when the server starts, then reuse it
# for every request. Loading it per-request would add ~3s of latency.
#
# Why a dict instead of a global variable?
# FastAPI's lifespan pattern uses a dict to share state safely.
# It's the recommended modern approach (replaces startup/shutdown events).

app_state: dict = {}


# ── Lifespan: runs on startup and shutdown ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before 'yield' runs at startup.
    Code after 'yield' runs at shutdown.

    We load the vector store here so it's ready for the first request.
    If ChromaDB doesn't exist yet, we print a warning but don't crash —
    the /ingest endpoint can be called first to create it.
    """
    print("🚀 Starting QA Support Bot API...")
    try:
        print("   Loading vector store from ChromaDB...")
        app_state["vector_store"] = load_vector_store()
        print("   ✅ Vector store loaded and ready.")
    except FileNotFoundError:
        print("   ⚠️  ChromaDB not found. Call POST /ingest first.")
        app_state["vector_store"] = None

    yield  # ← server is running while we're here

    # Shutdown cleanup (nothing needed for ChromaDB)
    print("Shutting down...")


# ── FastAPI app instance ───────────────────────────────────────────────
app = FastAPI(
    title="QA Support Bot",
    description=(
        "A RAG-powered Q&A bot that answers questions "
        "based only on crawled website content."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS middleware ────────────────────────────────────────────────────
# CORS = Cross-Origin Resource Sharing.
# Without this, a browser frontend on a different port/domain can't
# call this API. We allow all origins for development.
# In production, replace "*" with your actual frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Models ────────────────────────────────────────────────────
# Pydantic models define the shape of request and response bodies.
# FastAPI uses them to:
#   1. Validate incoming JSON automatically
#   2. Show accurate docs in Swagger UI
#   3. Give you IDE autocomplete


class AskRequest(BaseModel):
    """Request body for POST /ask"""
    question: str = Field(
        ...,                              # ... means required
        min_length=3,
        max_length=500,
        description="The question to ask the support bot",
        examples=["What is a Python list?"]
    )
    top_k: Optional[int] = Field(
        default=4,
        ge=1,                             # ge = greater than or equal
        le=10,
        description="Number of chunks to retrieve (1-10)"
    )


class AskResponse(BaseModel):
    """Response body for POST /ask"""
    question:    str
    answer:      str
    sources:     list[str]
    chunks_used: int


class IngestRequest(BaseModel):
    """Request body for POST /ingest"""
    url: Optional[str] = Field(
        default=None,
        description="Override the TARGET_URL from .env (optional)"
    )
    max_pages: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Max pages to crawl (overrides .env)"
    )


class StatusResponse(BaseModel):
    """Response body for GET /status"""
    status:        str
    vector_store:  str
    collection:    str


# ── Routes ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    """
    Health check endpoint.
    Returns 200 OK if the server is running.
    Used by Docker, load balancers, and monitoring tools.
    """
    return {
        "message": "QA Support Bot is running",
        "docs":    "/docs",
        "ask":     "POST /ask",
        "ingest":  "POST /ingest",
    }


@app.get("/status", response_model=StatusResponse, tags=["Health"])
async def status():
    """
    Check if the vector store is loaded and ready.
    Call this before /ask to make sure ingestion has been done.
    """
    from app.ingest import CHROMA_COLLECTION
    store_ready = app_state.get("vector_store") is not None

    return StatusResponse(
        status="ready" if store_ready else "not_ready",
        vector_store="loaded" if store_ready else "missing — run POST /ingest",
        collection=CHROMA_COLLECTION,
    )


@app.post("/ask", response_model=AskResponse, tags=["QA"])
async def ask_question(request: AskRequest):
    """
    Ask a question and get an answer grounded in crawled content.

    - Retrieves relevant chunks from ChromaDB
    - Builds a grounded prompt
    - Sends to Ollama (gemma3:4b)
    - Returns answer + source URLs

    If the bot can't find relevant context, it says so honestly
    instead of guessing.
    """
    # Check that the vector store is ready
    vector_store = app_state.get("vector_store")
    if vector_store is None:
        # 503 = Service Unavailable
        raise HTTPException(
            status_code=503,
            detail=(
                "Vector store not loaded. "
                "Please run POST /ingest first to crawl and index content."
            )
        )

    try:
        # Call our RAG pipeline from rag.py
        result = ask(
            question=request.question,
            vector_store=vector_store,
        )
        return AskResponse(**result)

    except ConnectionError:
        # Ollama server is not running
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot connect to Ollama. "
                "Make sure Ollama is running: `ollama serve`"
            )
        )
    except Exception as e:
        # Catch-all for unexpected errors
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@app.post("/ingest", tags=["Admin"])
async def trigger_ingest(request: IngestRequest):
    """
    Trigger a fresh crawl and re-ingest all content into ChromaDB.

    Use this when:
    - Setting up the bot for the first time
    - The target website has been updated
    - You want to change the crawl URL or depth

    Warning: This replaces existing ChromaDB data.
    It may take 1-3 minutes depending on MAX_PAGES.
    """
    from app.crawler import crawl
    from app.utils import TARGET_URL, MAX_PAGES

    try:
        # Use request params if provided, otherwise fall back to .env
        url       = request.url or TARGET_URL
        max_pages = request.max_pages or MAX_PAGES

        print(f"Starting ingestion: url={url}, max_pages={max_pages}")

        # Run crawl
        pages = crawl(start_url=url, max_pages=max_pages)

        if not pages:
            raise HTTPException(
                status_code=422,
                detail=f"No pages crawled from {url}. Check the URL."
            )

        # Run ingest (chunk + embed + store)
        vector_store = ingest(pages=pages)

        # Update the shared state so /ask uses the new data immediately
        app_state["vector_store"] = vector_store

        return {
            "status":      "success",
            "pages_crawled": len(pages),
            "message":     f"Successfully ingested {len(pages)} pages from {url}",
        }

    except HTTPException:
        raise  # re-raise HTTP errors as-is
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}"
        )