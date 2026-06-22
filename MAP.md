# 🗺 RAG-CRM Project Map

> Level 0 — Global context for all agents (Hermes + Paperclip)
> Always loaded first in any new session.

---

## Project Overview

| Field | Value |
|---|---|
| **Name** | RAG-CRM |
| **Path** | `/media/sf_VM_Share/Projects/AI/rag-crm/` |
| **Status** | DEV (Phase 0 — Infrastructure) |
| **Goal** | Hybrid RAG platform integrating with existing CRM |
| **Stack** | Python 3.12+, FastAPI, PostgreSQL + pgvector, LangGraph, Next.js |
| **LLM** | DeepSeek API (primary), Ollama (local fallback) |
| **Embeddings** | BGE-Small ONNX → BGE-M3 ONNX (later) |
| **Deployment** | Docker Compose (local) |

---

## Related Projects

| Project | Path | Status | Notes |
|---|---|---|---|
| CRM-SaaS | `/media/sf_VM_Share/Projects/AI/crm-saas/` | LIVE | RAG will integrate as query layer |
| RAG-CRM | `/media/sf_VM_Share/Projects/AI/rag-crm/` | DEV | This project |

---

## Infrastructure

| Component | Port | Container | Notes |
|---|---|---|---|
| Backend API | 8000 | `rag-backend` | FastAPI |
| Frontend | 3000 | `rag-frontend` | Next.js |
| PostgreSQL + pgvector | 5432 | `rag-db` | Primary + vector storage |
| Redis | 6379 | `rag-redis` | Cache / rate limiting |
| Ollama | 11434 | `rag-ollama` | Local LLM (future) |

---

## Feature Chain (Iterations)

Active: Iteration 0 (Infrastructure)
Next: Iteration 1 (Docker Compose + /health)

See `docs/roadmap.md` for full feature chain.
