# CLAUDE.md — RAG-CRM

> Level 1 — Project architecture & rules for AI agents.
> Read this before touching any source code.

---

## Architecture Overview

```
User Query
    ↓
[FastAPI] ← Query Agent
    ↓
[LangGraph State Machine]
    ├── Retrieval Agent  → pgvector (semantic) + BM25 (keyword) → RRF Fusion
    ├── Reranker Agent   → BGE-Reranker cross-encoder
    ├── Knowledge Agent  → LLM Wiki (markdown files)
    ├── Answer Agent     → DeepSeek / Ollama → final response
    ├── Critic Agent     → validates answer quality (blind)
    └── Memory Agent     → 4-layer memory (Session/Episodic/Semantic/Project)
```

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Vector store | pgvector (→ Qdrant future) | Shared DB with CRM, no extra infra |
| Hybrid search | pgvector FTS + rank_bm25 + RRF | True BM25 via Python, not PG tsvector |
| Embedding model | BGE-Small ONNX → BGE-M3 ONNX later | No GPU, ONNX gives 2-3x CPU speedup |
| Agent framework | Simple state machine → LangGraph v2 | Faster debug on early iterations |
| LLM | DeepSeek API (primary), Ollama (local) | API for speed, local for offline |
| Frontend | Streamlit (MVP) → Next.js (v2) | Ship in 2 days, not 2 weeks |

---

## Critical Rules (enforced by Critic Agent)

1. **Three witnesses rule** — Every response must be verified by ≥2 independent methods (LLM + code + second LLM)
2. **Blind calculation** — Agent never sees the "expected" answer while generating
3. **Temperature 0** — For retrieval, ranking, and factual generation
4. **Step-by-step required** — Every answer must include intermediate reasoning in JSON
5. **"I don't know" is allowed** — Never hallucinate; say "insufficient data"
6. **Anchor tests first** — 5-10 known-ground-truth queries must pass before any new feature is accepted
7. **Invariants** — Results must satisfy: non-null, sources cited, confidence > 0.3

---

## Key Files

| Path | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI entry point |
| `backend/app/core/config.py` | Settings (Pydantic) |
| `backend/app/core/database.py` | SQLAlchemy + pgvector |
| `backend/app/retrieval/` | Semantic, keyword, hybrid, reranker |
| `backend/app/agents/workflow.py` | LangGraph state machine |
| `backend/app/ingestion/` | Document pipeline |
| `backend/app/knowledge/wiki.py` | LLM Wiki maintenance |
| `infrastructure/docker-compose.yml` | All services |

---

## Commands

| Action | Command |
|---|---|
| Start stack | `docker compose -f infrastructure/docker-compose.yml up -d` |
| Backend tests | `cd backend && pytest` |
| Run migration | `cd backend && alembic upgrade head` |
| Seed anchors | `cd backend && python scripts/seed_anchors.py` |
| Format code | `ruff check --fix . && ruff format .` |

---

## Workflow (BOSS → Paperclip)

1. **I (Hermes)** define the task + acceptance criteria
2. **Paperclip AI agents** implement
3. **OCR (Open Code Review)** — deterministic code quality check
4. **Anchor tests** — must pass all 5-10 known queries
5. **Integration tests** — must not break existing features
6. **Review / ACCEPT or RETRY** — decision by Hermes

**No iteration advances without passing all checks from the previous iteration.**
