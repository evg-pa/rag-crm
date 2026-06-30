FROM python:3.12-slim AS builder

WORKDIR /app
# ---------- Layer 1: ML dependencies (fat, rarely changes) ----------
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

# ---------- Layer 2: App dependencies (lean, changes when we add features) ----------
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

# ---------- Layer 3: Dev dependencies ----------
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# --- Runner stage ---
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY tests/ ./tests/

# Pre-download embedding model and reranker
RUN python3 /app/app/scripts/preload_models.py 2>&1 || echo "preload failed (will download on first use)"

# Create non-root user with writable home for HuggingFace cache
RUN groupadd -r appuser 2>/dev/null || true; useradd -r -g appuser appuser 2>/dev/null || true; \
    chmod -R o+rX /app/app 2>/dev/null || true; \
    mkdir -p /app/.cache && chown appuser:appuser /app/.cache 2>/dev/null || true; \
    mkdir -p /app/.cache/huggingface && chown appuser:appuser /app/.cache/huggingface 2>/dev/null || true
ENV HF_HOME=/app/.cache/huggingface
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

ENV OPENAI_API_KEY=***
ENV LLM_BASE_URL=https://api.deepseek.com
ENV LLM_MODEL=deepseek-chat

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
