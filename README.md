# RAG-CRM

Retrieval-Augmented Generation CRM — a multi-agent RAG system with CRM integration.

[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docs.docker.com/compose/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](#license)

---

## ✨ One-command Setup

```bash
git clone <repo-url> && cd rag-crm
./setup.sh
```

The script will:

| Step | What it does |
|------|-------------|
| 1 | Check Docker & Docker Compose are installed |
| 2 | Create `.env` from `.env.example` (won't overwrite existing) |
| 3 | Prompt for your **DeepSeek API key** (or skip for fallback mode) |
| 4 | Start all services via `docker compose up -d` |
| 5 | Wait for the backend to become healthy, then print URLs |

That's it. Open **http://localhost:8501** for the dashboard.

---

## Manual Quick Start

### Prerequisites

- Docker & Docker Compose

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

---

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

| Service  | Port | Description        |
|----------|------|--------------------|
| Backend  | 8000 | FastAPI REST API   |
| Frontend | 8501 | Streamlit Dashboard|
| Postgres | 5432 | pgvector + pgvector|
| Redis    | 6379 | Caching & sessions |

## Development

```bash
cd backend
uvicorn app.main:app --reload
```
