FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    "uvicorn[standard]>=0.30.0" \
    "sqlalchemy[asyncio]>=2.0.30" \
    asyncpg>=0.29.0 \
    pydantic>=2.7.0 \
    pydantic-settings>=2.3.0 \
    redis>=5.0.0 \
    structlog>=24.0.0 \
    httpx>=0.27.0

# Copy application code
COPY app/ ./app/

# Fix permissions so non-root user can read
RUN chmod -R o+rX /app/app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
