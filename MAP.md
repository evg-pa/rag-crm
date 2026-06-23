# 🗺 RAG-CRM Project Map

> Level 0 — Global context for all agents (Hermes + Paperclip)
> Always loaded first in any new session.

---

## Project Overview

| Field | Value |
|---|---|
| **Name** | RAG-CRM |
| **Path** | `/media/sf_VM_Share/Projects/AI/rag-crm/` |
| **Status** | DEV (Phase 12 — Observability & Scale ⏳) |
| **Goal** | Hybrid RAG platform integrating with existing CRM |
| **Stack** | Python 3.12+, FastAPI, PostgreSQL + pgvector, LangGraph |
| **LLM** | DeepSeek API (primary, no Ollama) |
| **Embeddings** | BGE-Small ONNX, rank_bm25, BGE-Reranker (80MB) |
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
| Backend API | 8000 | `rag-backend` | FastAPI, healthy |
| PostgreSQL + pgvector | 5432 | `rag-db` | Primary + vector storage, healthy |
| Redis | 6379 | `rag-redis` | Cache / rate limiting, healthy |

---

## Iteration Status

| # | Name | Paperclip | Code | Status |
|---|---|---|---|---|
| 1 | Core Infrastructure (Docker + FastAPI) | ✅ | ✅ | Done |
| 2 | Document Ingestion | ✅ | ✅ | Done |
| 3 | Embeddings + Semantic Search | ✅ | ✅ | Done |
| 4 | Hybrid Search (BM25 + Reranker) | ✅ | ✅ | Done |
| 5 | DeepSeek Q&A | ✅ | ✅ | Done |
| 6 | Multi-Agent LangGraph Pipeline | ✅ | ✅ | Done |
| 7 | Knowledge Agent | APP-134 | ✅ | Done |
| 8 | LLM Wiki | APP-137 | ✅ | Done |
| 9 | Memory System | APP-138 | ✅ | Done |
| **10** | **Full Ingestion Pipeline** | **APP-136/139** | **✅** | **Done** |
| **11** | **Streamlit Frontend** | **APP-144** | **✅** | **Done** |
| **12** | **Observability & Scale** | **—** | **—** | **⏳ Not started** |

See `docs/roadmap.md` for full feature chain and acceptance criteria.
