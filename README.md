# QA Support Bot

A Retrieval-Augmented Generation (RAG) support bot that answers questions using only the content crawled from a target website. If the answer isn't in the crawled content, the bot says so instead of guessing.

## Overview

Given a website URL, the bot:

1. Crawls the site and extracts clean text from each page.
2. Cleans and splits the text into overlapping chunks.
3. Generates embeddings for each chunk using a local sentence-transformer model.
4. Stores the chunks and embeddings in a ChromaDB vector store.
5. At query time, retrieves the most relevant chunks for a question, builds a grounded prompt, and asks an OpenAI model to answer using only that context.
6. Returns the answer along with the source URLs it was built from.

## Tech Stack

| Component                | Technology                                              |
|---------------------------|----------------------------------------------------------|
| API framework              | FastAPI + Uvicorn                                          |
| LLM                          | OpenAI `gpt-4o-mini`                                          |
| Embeddings                    | `sentence-transformers` (`all-MiniLM-L6-v2`, local, 384-dim)    |
| Vector database                | ChromaDB (persisted to disk)                                     |
| Chunking / orchestration         | LangChain (`RecursiveCharacterTextSplitter`)                       |
| Web crawling                       | Requests + BeautifulSoup4                                          |
| Containerization                     | Docker + Docker Compose                                              |
| Config                                  | python-dotenv                                                          |

## Project Structure

```
qa-support-bot/
├── app/
│   ├── main.py        # FastAPI app: routes, startup/shutdown, CORS
│   ├── crawler.py      # Site crawler: BFS link discovery, text extraction
│   ├── ingest.py        # Cleaning, chunking, embedding, and storage pipeline
│   ├── rag.py            # Retrieval + prompt construction + answer generation
│   ├── prompts.py        # Prompt templates
│   └── utils.py           # Environment/config loading
├── chroma_db/             # Persisted vector store (created on first ingest, git-ignored)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Prerequisites

- Python 3.11+
- An OpenAI API key
- Git

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Anurag-YadavIIH/qa-support-bot.git
cd qa-support-bot
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set the required values:

| Variable             | Required | Default        | Description                          |
|-----------------------|----------|-----------------|----------------------------------------|
| `OPENAI_API_KEY`       | Yes      | —                | Your OpenAI API key                    |
| `TARGET_URL`            | Yes      | —                | Website to crawl                       |
| `MAX_PAGES`             | No       | `10`             | Max pages crawled per ingestion run    |
| `OPENAI_MODEL`          | No       | `gpt-4o-mini`    | OpenAI chat model used for generation  |
| `CHROMA_COLLECTION`     | No       | `support_bot`    | ChromaDB collection name               |

### 5. Build the vector index

```bash
python -m app.ingest
```

This crawls `TARGET_URL`, cleans and chunks the text, generates embeddings, and stores them in ChromaDB at `./chroma_db`. The first run also downloads the embedding model (~80 MB).

### 6. Start the API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`.

## Running with Docker

```bash
cp .env.example .env   # add your OPENAI_API_KEY
docker compose up --build
```

Once the container is running, trigger ingestion (first time only):

```bash
curl -X POST http://localhost:8000/ingest
```

## API Reference

### `GET /`

Health check.

```json
{
  "message": "QA Support Bot is running",
  "docs": "/docs",
  "ask": "POST /ask",
  "ingest": "POST /ingest"
}
```

### `GET /status`

Reports whether the vector store is loaded and ready.

```json
{
  "status": "ready",
  "vector_store": "loaded",
  "collection": "support_bot"
}
```

### `POST /ask`

Ask a question grounded in the crawled content.

Request body:

```json
{
  "question": "What is a Python list?",
  "top_k": 4
}
```

| Field      | Type    | Required | Default | Description                          |
|-------------|---------|----------|---------|----------------------------------------|
| `question`  | string  | Yes      | —       | Question text (3–500 characters)       |
| `top_k`     | integer | No       | `4`     | Number of chunks to retrieve (1–10)    |

Response:

```json
{
  "question": "What is a Python list?",
  "answer": "A Python list is an ordered, mutable collection that can hold items of any data type...",
  "sources": [
    "https://docs.python.org/3/tutorial/introduction.html",
    "https://docs.python.org/3/tutorial/datastructures.html"
  ],
  "chunks_used": 4
}
```

If no relevant content is found, the bot returns a fallback answer with an empty `sources` list instead of calling the LLM:

```json
{
  "question": "Who won the FIFA World Cup?",
  "answer": "I couldn't find any relevant information in my knowledge base to answer your question. Please try rephrasing, or ask about topics covered on the website.",
  "sources": [],
  "chunks_used": 0
}
```

| Status | Meaning                  | Fix                                   |
|--------|---------------------------|------------------------------------------|
| 422    | Invalid request body       | Check `question` length and types        |
| 503    | Vector store not loaded     | Call `POST /ingest` first                 |
| 503    | OpenAI unreachable           | Check `OPENAI_API_KEY` in `.env`          |

### `POST /ingest`

Crawls the target site and rebuilds the ChromaDB index.

Request body (all fields optional, fall back to `.env`):

```json
{
  "url": "https://docs.python.org/3/tutorial/",
  "max_pages": 10
}
```

Response:

```json
{
  "status": "success",
  "pages_crawled": 10,
  "message": "Successfully ingested 10 pages from https://docs.python.org/3/tutorial/"
}
```

## How Hallucinations Are Prevented

| Stage      | Technique                                              | Effect                                                        |
|-------------|----------------------------------------------------------|-----------------------------------------------------------------|
| Retrieval   | Cosine similarity threshold (`MIN_SCORE = 0.3`)            | Irrelevant chunks are discarded before reaching the LLM            |
| Retrieval   | Empty-context short-circuit                                | If no chunk passes the threshold, the LLM is never called          |
| Prompt      | Explicit "use only the provided context" instruction        | Model is told not to draw on outside training knowledge            |
| Prompt      | Reinforced via the system message                           | A second layer of grounding instructions                           |
| Generation  | Low temperature (`0.1`)                                      | Keeps answers factual rather than creative                         |
| Response    | Source URLs always included                                  | Every answer can be traced back to the source page                 |

## Testing the API

### curl

```bash
curl http://localhost:8000/

curl http://localhost:8000/status

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is a Python list?"}'

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'

curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"max_pages": 5}'
```

### Postman

1. Create a new `POST` request to `http://localhost:8000/ask`.
2. Set the body to raw JSON: `{"question": "How do I use a for loop in Python?"}`.
3. Send the request and confirm the response includes an `answer` and a non-empty `sources` array for in-scope questions.

### Swagger UI

Visit `http://localhost:8000/docs` for an interactive interface to exercise every endpoint without writing any code.

## Design Notes

**Local embeddings instead of OpenAI embeddings.** Embeddings are generated once during ingestion and reused indefinitely. A local `sentence-transformers` model avoids per-chunk API costs and keeps the indexing step fully offline.

**ChromaDB instead of a hosted vector database.** ChromaDB persists to disk with no external service or account required, which is appropriate for the scale of this project.

**Overlapping chunks (100-character overlap).** Without overlap, sentences that fall on a chunk boundary get split across two chunks, with neither containing the full thought. Overlap ensures boundary content is captured intact in at least one chunk.

**Low generation temperature (0.1).** Lower temperature reduces paraphrasing drift, keeping answers anchored to the retrieved context rather than the model's own phrasing tendencies.

## Troubleshooting

| Symptom                              | Likely Cause                              | Fix                                            |
|----------------------------------------|----------------------------------------------|---------------------------------------------------|
| `Missing required environment variable` | `.env` not configured                        | Copy `.env.example` to `.env` and fill in values     |
| `ChromaDB not found`                    | Ingestion not run yet                         | Run `python -m app.ingest`                          |
| `503` on `/ask`                          | Vector store not loaded                        | Call `POST /ingest` first                            |
| `0 chunks created`                        | Crawled pages had no usable text                | Verify `TARGET_URL`, or try a different site          |
| All answers are the fallback message      | `MIN_SCORE` threshold too high                  | Lower it in `app/rag.py`                              |
| Crawler returns 0 pages                    | Site blocks bots or is JavaScript-rendered        | Try a static documentation site                  |

## License

MIT
