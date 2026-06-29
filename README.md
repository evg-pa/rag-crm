# RAG-CRM

Retrieval-Augmented Generation CRM — a multi-agent RAG system that understands your documents using a neural network (LLM).

[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docs.docker.com/compose/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](#license)

> ⚡ **Quick start** — pre-built images, no local build needed.
> `chmod +x setup.sh && ./setup.sh` → ready in ~1 minute.

---

## One-command setup

```bash
chmod +x setup.sh
./setup.sh
```

**Before:** 10-15 minutes (local Docker build with pytorch + transformers)  
**Now:** ~1 minute (pulls pre-built images from GitHub Container Registry)

You'll be guided to pick an **LLM provider** and paste your API key.

**Supported providers:** DeepSeek, DeepSeek V4 Flash, OpenAI, Together AI, Groq, OpenRouter, OpenModel, or any custom OpenAI-compatible endpoint.

### Quick examples

```bash
# Interactive (choose provider from a menu)
chmod +x setup.sh && ./setup.sh

# DeepSeek (default)
./setup.sh -k sk-xxx

# DeepSeek V4 Flash (Nous Research fine-tune)
./setup.sh -k sk-xxx -u https://api.deepseek.com/v1 -m deepseek-v4-flash

# OpenAI
./setup.sh -k sk-xxx -u https://api.openai.com -m gpt-4o-mini

# Together AI
./setup.sh -k sk-xxx -u https://api.together.xyz -m mistralai/Mixtral-8x7B-Instruct-v0.1

# Groq
./setup.sh -k gsk-xxx -u https://api.groq.com/openai -m llama3-70b-8192

# OpenRouter (any model from their catalog)
./setup.sh -k sk-xxx -u https://openrouter.ai/api/v1 -m openai/gpt-4o-mini

# OpenModel (unified gateway — one key for any provider)
./setup.sh -k om-xxx -u https://api.openmodel.ai -m openai/gpt-4o
```

The script handles everything: creates the config, starts all services, and waits for everything to be healthy.

---

## Manual setup (still fast, no build)

```bash
cp .env.example .env                   # Create config
# Edit .env — set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

docker compose -f infrastructure/docker-compose.yml pull   # ~1 min
docker compose -f infrastructure/docker-compose.yml up -d  # ~30 sec
```

Check: `curl http://localhost:8000/health/ready`

---

## Local development (build from source)

```bash
# Override: build images locally instead of pulling
docker compose -f infrastructure/docker-compose.yml \
              -f infrastructure/docker-compose.dev.yml up -d

# Or run backend directly on your host
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

---

## What happens without a key?

RAG will still run and index your documents — but the AI won't be able to answer questions about them. You can add a key later by editing `.env` and restarting:

```bash
# Edit .env — set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
docker compose -f infrastructure/docker-compose.yml restart backend
```

---

## After setup

| Service | URL | What it does |
|----------|-----|-------------|
| Dashboard | http://localhost:8501 | Upload documents, ask questions, browse search |
| API docs  | http://localhost:8000/docs | Interactive API reference |
| Health    | http://localhost:8000/health/ready | Check all services are green |

---

## LLM Providers

| Provider | Base URL | Example Model | Hint |
|----------|----------|---------------|------|
| **DeepSeek** | `https://api.deepseek.com` | `deepseek-chat` | Default — cheap & capable |
| **DeepSeek V4 Flash** | `https://api.deepseek.com/v1` | `deepseek-v4-flash` | Nous Research fine-tune, very fast |
| **OpenAI** | `https://api.openai.com` | `gpt-4o-mini` | Most compatible, higher cost |
| **Together AI** | `https://api.together.xyz` | `mistralai/Mixtral-8x7B-Instruct-v0.1` | Good open models, cheap |
| **Groq** | `https://api.groq.com/openai` | `llama3-70b-8192` | Fastest inference (LPU) |
| **OpenRouter** | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` | Gateway to 200+ models |
| **OpenModel** | `https://api.openmodel.ai` | `openai/gpt-4o` | Unified gateway — one key for OpenAI, Anthropic, DeepSeek, Google, and more |

> **Tip:** Any OpenAI-compatible endpoint works — just set `LLM_BASE_URL` and `LLM_MODEL` in `.env`.

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
