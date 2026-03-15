FROM python:3.12-slim

WORKDIR /app

# System deps (faiss-cpu needs libgomp)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

# Copy application source
COPY server.py config.py db.py embeddings.py ingestion.py llm.py retrieval.py ./
COPY src/ src/

# Runtime data directory (mounted as volume)
RUN mkdir -p /app/data/indices

# Non-root user
RUN useradd -m -u 1000 nexus && chown -R nexus:nexus /app
USER nexus

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf -X POST http://localhost:8765/mcp \
        -H 'Content-Type: application/json' \
        -H 'Accept: application/json, text/event-stream' \
        -d '{"jsonrpc":"2.0","id":0,"method":"ping"}' || exit 1

CMD ["python", "server.py"]
