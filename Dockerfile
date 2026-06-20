# Dockerfile
# Defines how to build the FastAPI app container image.
#
# Think of this as a recipe:
# "Start with Python, copy my code, install dependencies, run the server"

# ── Base image ─────────────────────────────────────────────────────────
# python:3.11-slim = Python 3.11 on minimal Debian Linux (~130MB)
# Why "slim"? The full image is ~900MB. Slim strips docs and extra tools
# we don't need, keeping our final image lean and fast to deploy.
FROM python:3.11-slim

# ── Set working directory ──────────────────────────────────────────────
# All subsequent commands run from /app inside the container.
# This is the standard convention for Python apps.
WORKDIR /app

# ── System dependencies ────────────────────────────────────────────────
# Some Python packages need system-level C libraries to compile.
# We install them here before installing Python packages.
#
# build-essential = C compiler (needed by some pip packages)
# curl            = used in healthcheck below
# && rm -rf /var/lib/apt/lists/* cleans the apt cache → smaller image
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ────────────────────────────────────────
# We copy requirements.txt FIRST (before the rest of the code).
#
# Why copy requirements separately?
# Docker builds in layers. If requirements.txt hasn't changed,
# Docker reuses the cached pip install layer — making rebuilds
# much faster. Only copy app code changes when you edit your .py files.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application code ──────────────────────────────────────────────
# Now copy everything else. This layer changes often (every code edit),
# but it's fast since we already installed dependencies above.
COPY . .

# ── Create data directories ────────────────────────────────────────────
# Ensure these exist inside the container.
# chroma_db/ will be mounted as a volume (data persists between restarts)
RUN mkdir -p data chroma_db

# ── Expose port ────────────────────────────────────────────────────────
# Tell Docker this container listens on port 8000.
# This is documentation — the actual port mapping is in docker-compose.yml
EXPOSE 8000

# ── Health check ───────────────────────────────────────────────────────
# Docker periodically runs this to check if the container is healthy.
# If it fails 3 times, Docker marks the container as "unhealthy".
# interval: check every 30s
# timeout:  give up after 10s
# retries:  mark unhealthy after 3 failures
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# ── Start command ──────────────────────────────────────────────────────
# This runs when the container starts.
# No --reload in production (that's only for development).
# --host 0.0.0.0 = listen on all interfaces inside the container
# --workers 1    = one worker process (enough for this project)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]