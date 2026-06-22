# Iteration 1 — Paperclip Task

## Goal
Set up the core infrastructure and bring the RAG-CRM project online:
Docker Compose (PostgreSQL + pgvector + Redis) + FastAPI skeleton with /health endpoint.

## Acceptance Criteria

1. `docker compose up -d` starts PostgreSQL (port 5432) with pgvector extension enabled, Redis (port 6379)
2. FastAPI app starts on port 8000
3. `GET /localhost:8000/health` returns `{"status":"ok","version":"0.1.0","database":"connected"}`
4. All Python code is typed (mypy strict mode), follows Clean Architecture with Repository Pattern
5. No hardcoded secrets — all config via env vars / .env
6. README updated with Quick Start instructions

## Files to Create

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/pyproject.toml`
Python project metadata with dependencies:
```toml
[project]
name = "rag-crm-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg",
    "psycopg2-binary",
    "alembic",
    "pydantic>=2.0",
    "pydantic-settings",
    "redis[hiredis]",
    "python-dotenv",
    "structlog",
    "httpx",
]
```

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/__init__.py`

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/main.py`
FastAPI application with lifespan, CORS middleware, health endpoint:
- `GET /health` — returns status, version, db connectivity
- `GET /` — redirect to /docs (Swagger UI)
- Lifespan handler for DB connection pool lifecycle
- CORS allowed for localhost:3000 (future Next.js frontend)

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/core/__init__.py`

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/core/config.py`
Pydantic BaseSettings with:
- `DATABASE_URL` (default: `postgresql+asyncpg://rag_user:rag_pass@localhost:5432/rag_crm`)
- `REDIS_URL` (default: `redis://localhost:6379/0`)
- `APP_NAME`, `APP_VERSION`, `LOG_LEVEL`
- `DEEPSEEK_API_KEY` (optional, for later)
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `EMBEDDING_MODEL`, `EMBEDDING_DIM`
- `RERANKER_MODEL`

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/core/database.py`
SQLAlchemy 2.0 async engine + session factory + Base declarative.
- `get_db()` async dependency
- Connection pool (5 min, 20 max)
- Health check query: `SELECT 1`

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/core/dependencies.py`
FastAPI dependency injection container:
- `get_settings()` — returns config singleton
- `get_db()` — yields async DB session
- `get_redis()` — yields Redis connection

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/core/logging.py`
Structured logging with structlog:
- JSON output in production, colored console in dev
- Request ID middleware

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/api/__init__.py`
Router aggregator

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/app/api/health.py`
Health router:
- `GET /health` — checks DB ping, returns JSON with status/version/db_connected
- `GET /health/ready` — readiness probe (same as health)
- `GET /health/live` — liveness probe (lightweight)

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/Dockerfile`
Multi-stage Dockerfile:
1. Builder: install deps, copy code
2. Runner: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### `infrastructure/docker-compose.yml` (UPDATE existing file)
Add backend service:
- Environment vars from `.env`
- Depends on postgres (healthcheck) + redis (healthcheck)
- Volume mount for live reload in dev
- Port 8000
- Healthcheck: `curl -f http://localhost:8000/health`

### `/media/sf_VM_Share/Projects/AI/rag-crm/.env` (CREATE from .env.example)
Copy .env.example → .env with actual values.

### `/media/sf_VM_Share/Projects/AI/rag-crm/README.md`
Quick start: prerequisites, setup, running, testing.

## Tests

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/tests/__init__.py`

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/tests/conftest.py`
Pytest fixtures:
- Async client (httpx.AsyncClient + FastAPI)
- Test DB session (separate DB or in-memory SQLite for unit tests)

### `/media/sf_VM_Share/Projects/AI/rag-crm/backend/tests/test_health.py`
```python
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["database"] == "connected"

async def test_health_db_integration(client):
    """Actually hits the DB through the API"""
    response = await client.get("/health")
    assert response.json()["database"] == "connected"
```

## Constraints (from Habr articles)

1. **Temperature 0** — even in config, set default temperature to 0
2. **Step-by-step not required yet** (Iteration 1 is infrastructure only)
3. **No LLM calls in Iteration 1** — this is pure backend skeleton
4. **Comment every env var** — inspired by CLAUDE.md approach
5. **All Python code must pass `ruff check` and `mypy --strict`** before PR

## Delivery Checklist

- [ ] All files created with correct paths
- [ ] `docker compose up -d --build` starts all services
- [ ] `curl localhost:8000/health` returns 200
- [ ] `pytest` passes all tests (min 2 tests)
- [ ] `ruff check .` passes with 0 errors
- [ ] `mypy --strict` passes with 0 errors
- [ ] README updated
