---
name: rag-crm
description: Hybrid RAG CRM platform — local, open-source, PostgreSQL + pgvector + LangGraph + DeepSeek. Covers document ingestion, vector search, knowledge agent, memory system, QA pipeline.
---

# RAG-CRM

Hybrid RAG CRM platform built with:
- **Backend**: FastAPI, SQLAlchemy 2, Pydantic v2
- **Database**: PostgreSQL 16 + pgvector, Redis 7
- **Embedding**: BGE-Small ONNX, rank_bm25, BGE-Reranker
- **LLM**: DeepSeek API via LangGraph
- **Architecture**: REST API, Docker Compose, hybrid search (dense + sparse + rerank)

## Key Endpoints

- `POST /documents/upload` — ingest documents
- `POST /qa` — ask questions (LangGraph pipeline)
- `GET /wiki/{id}` — knowledge agent summary
- `GET/POST /memory/*` — memory system (working/episodic/semantic/procedural)

## Agent Notes

- Backend runs in Docker at `localhost:8000`
- Source at `/media/sf_VM_Share/Projects/AI/rag-crm`
- Docker compose: `infrastructure/docker-compose.yml`
