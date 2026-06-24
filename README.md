# RAG-CRM

Retrieval-Augmented Generation CRM — a multi-agent RAG system that understands your documents using a neural network (LLM).

[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docs.docker.com/compose/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](#license)

---

## ✨ One-command setup

```bash
./setup.sh
```

You'll be prompted for a **DeepSeek API key** — this connects a neural network so RAG can answer your questions about documents.

> **Where to get a key:** Sign up at [platform.deepseek.com](https://platform.deepseek.com/api_keys) (free credits available).

To skip the prompt, pass the key directly:

```bash
./setup.sh -k ***
```

Or with `curl` for a fully scripted install:

```bash
curl -sL https://your-repo-url/raw/setup.sh | bash -s -- -k ***
```

The script handles everything: creates the config, starts all services, and waits for everything to be healthy.

---

## What happens without a key?

RAG will still run and index your documents — but the AI won't be able to answer questions about them. You can add a key later by editing `.env` and restarting:

```bash
# Edit .env with your key, then:
docker compose -f infrastructure/docker-compose.yml restart backend
```

---

## After setup

Open **http://localhost:8501** for the dashboard.

| Service  | URL | What it does |
|----------|-----|-------------|
| Dashboard | http://localhost:8501 | Upload documents, ask questions, browse search |
| API docs  | http://localhost:8000/docs | Interactive API reference |
| Health    | http://localhost:8000/health/ready | Check all services are green |

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

## Manual setup

```bash
cp .env.example .env       # Create config
# Edit .env — add DEEPSEEK_API_KEY

docker compose -f infrastructure/docker-compose.yml up -d
```

## Development

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```
