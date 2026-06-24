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

You'll be guided to pick an **LLM provider** and paste your API key — this connects a neural network so RAG can answer your questions about documents.

**Supported providers:** DeepSeek, OpenAI, Together AI, Groq, OpenRouter, or any custom OpenAI-compatible endpoint.

### Quick examples

```bash
# Interactive (choose provider from a menu)
./setup.sh

# DeepSeek (default)
./setup.sh -k ***

# OpenAI
./setup.sh -k *** -u https://api.openai.com -m gpt-4o-mini

# Together AI
./setup.sh -k *** -u https://api.together.xyz -m mistralai/Mixtral-8x7B-Instruct-v0.1

# Groq
./setup.sh -k *** -u https://api.groq.com/openai -m llama3-70b-8192

# OpenRouter
./setup.sh -k *** -u https://openrouter.ai/api/v1 -m openai/gpt-4o-mini
```

The script handles everything: creates the config, starts all services, and waits for everything to be healthy.

---

## What happens without a key?

RAG will still run and index your documents — but the AI won't be able to answer questions about them. You can add a key later by editing `.env` and restarting:

```bash
# Edit .env — set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
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
  ├── Answer Agent     → Any OpenAI-compatible LLM
  ├── Critic Agent     → Answer validation
  └── Memory Agent     → 4-layer memory
```

## Manual setup

```bash
cp .env.example .env       # Create config
# Edit .env — set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

docker compose -f infrastructure/docker-compose.yml up -d
```

## Development

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```
