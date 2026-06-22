FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies and project
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    "uvicorn[standard]>=0.30.0" \
    "sqlalchemy[asyncio]>=2.0.30" \
    asyncpg>=0.29.0 \
    alembic>=1.13.0 \
    pydantic>=2.7.0 \
    pydantic-settings>=2.3.0 \
    redis>=5.0.0 \
    structlog>=24.0.0 \
    httpx>=0.27.0 \
    python-multipart>=0.0.7 \
    "optimum[onnxruntime]>=1.24.0" \
    pgvector>=0.4.0 \
    "rank-bm25>=0.2.2" \
    "transformers>=4.46.0" \
    "torch>=2.0.0"

# --- Runner stage ---
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/

# Pre-download embedding model and reranker for faster first-request
RUN python3 -c "\
from huggingface_hub import snapshot_download;\
snapshot_download(repo_id='BAAI/bge-small-en-v1.5', ignore_patterns=['*.h5','*.msgpack']);\
snapshot_download(repo_id='BAAI/bge-reranker-v2-m3', ignore_patterns=['*.h5','*.msgpack','*.safetensors']);\
" 2>&1 | tail -3 || echo "pre-download skipped (will download on first use)"

# Create non-root user with writable home for HuggingFace cache
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chmod -R o+rX /app/app && \
    mkdir -p /app/.cache && chown appuser:appuser /app/.cache && \
    mkdir -p /app/.cache/huggingface && chown appuser:appuser /app/.cache/huggingface
ENV HF_HOME=/app/.cache/huggingface
USER appuser

EXPOSE 8000

ENV OPENAI_API_KEY=""
ENV DEEPSEEK_API_KEY=""

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
