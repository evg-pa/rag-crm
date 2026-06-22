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
    httpx>=0.27.0

# --- Runner stage ---
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chmod -R o+rX /app/app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
