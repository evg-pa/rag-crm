# RAG-CRM

Retrieval-Augmented Generation CRM — a multi-agent RAG system with CRM integration.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+

### 1. Set up environment

```bash
cp .env.example .env
# Edit .env to add your DEEPSEEK_API_KEY
```

### 2. Start the stack

```bash
docker compose -f infrastructure/docker-compose.yml up -d
```

### 3. Verify

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

### 4. Run tests (local dev)

```bash
cd backend
pip install -e ".[dev]"
pytest
ruff check .
mypy app/
```

## Architecture

```
User Query → FastAPI → LangGraph State Machine
  ├── Retrieval Agent  → pgvector + BM25 → RRF Fusion
  ├── Reranker Agent   → BGE-Reranker
  ├── Knowledge Agent  → LLM Wiki
  ├── Answer Agent     → DeepSeek / Ollama
  ├── Critic Agent     → Answer validation
  └── Memory Agent     → 4-layer memory
```

## Services

| Service  | Port  | Description          |
| -------- | ----- | -------------------- |
| Backend  | 8000  | FastAPI REST API     |
| Postgres | 5432  | pgvector + pgvector  |
| Redis    | 6379  | Caching & sessions   |

## Development

```bash
cd backend
uvicorn app.main:app --reload
```
