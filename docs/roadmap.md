# RAG-CRM — Implementation Roadmap

## Strategy: Simple → Complex

Each iteration produces a **working, tested feature** before the next begins.
BOSS (Hermes) delegates to Paperclip agents → OCR QA → Anchor tests → ACCEPT / RETRY.

---

## Phase 0: Infrastructure & Context (current)

- [x] Project structure created
- [x] MAP.md (Level 0)
- [x] CLAUDE.md (Level 1)
- [x] DECISIONS.md
- [x] Architecture doc (docs/architecture.md)
- [ ] Docker Compose with PostgreSQL + pgvector + Redis
- [ ] Python venv with dependencies
- [ ] Git init + first commit

---

## Phase 1: Core Backend (Iterations 1-2)

### Iteration 1 — Docker + FastAPI skeleton
Goal: `docker compose up` → `GET /health` returns 200

Backend: FastAPI app with config, database, health endpoint
Infra: Docker Compose (PostgreSQL 16 + pgvector, Redis)
Test: `curl localhost:8000/health` → `{"status":"ok"}`

**Acceptance:** 5 anchor health checks pass

### Iteration 2 — Document Ingestion (basic)
Goal: Upload .md/.txt → parsed → chunked → stored in DB

Backend: Upload endpoint, text parser, chunker, SQLAlchemy models
Test: Upload file → check DB for parsed chunks

**Acceptance:** 3 test files ingested correctly

---

## Phase 2: Search (Iterations 3-5)

### Iteration 3 — Embeddings + Semantic Search
Goal: BGE-Small ONNX → pgvector → search by meaning

Backend: Embedding service, pgvector index, semantic search endpoint
Test: "payment methods" finds document about payments

**Acceptance:** Semantic search returns relevant results (recall@5 > 0.7)

### Iteration 4 — BM25 + Hybrid Search
Goal: Keyword search + RRF fusion with semantic

Backend: rank_bm25 index, hybrid search, RRF scoring
Test: "payment" keyword query matches + hybrid better than either alone

**Acceptance:** Hybrid search outperforms pure semantic or pure BM25 (nDCG@10)

### Iteration 5 — Reranker
Goal: BGE-Reranker cross-encoder reranks top-20

Backend: Reranker service, rerank endpoint
Test: Reranked results have better order than raw hybrid

**Acceptance:** Reranker improves MRR by ≥10% over raw hybrid

---

## Phase 3: Answer Generation (Iterations 6-7)

### Iteration 6 — Single Agent Q&A
Goal: Retrieved context + LLM → answer with citations

Backend: Answer Agent (DeepSeek API + Ollama fallback), context builder
Test: "What does this project do?" → correct answer from ingested docs

**Acceptance:** Answers are factual, cite sources, pass 5 anchor queries

### Iteration 7 — Multi-Agent LangGraph
Goal: 7 agents communicating through LangGraph state

Backend: LangGraph workflow, all agent implementations, state machine
Test: End-to-end flow Query→Retrieve→Rerank→Answer→Critic

**Acceptance:** Full pipeline end-to-end, Critic catches intentional errors

---

## Phase 4: Knowledge & Memory (Iterations 8-9)

### Iteration 8 — Knowledge Agent + LLM Wiki
Goal: Auto-generated document summaries in `wiki/` as markdown

Backend: Knowledge synthesis, wiki CRUD, auto-update on ingestion
Test: Ingest doc → wiki has summary → search finds it

**Acceptance:** Wiki markdown files are valid, contain accurate summaries

### Iteration 9 — Memory System
Goal: 4 memory types with automatic lifecycle

Backend: Session, Episodic, Semantic, Project memory stores
Test: Query → check session memory → ask again → memory found

**Acceptance:** Cross-session context preserved, memory doesn't grow unbounded

---

## Phase 5: Full Features (Iterations 10-12)

### Iteration 10 — Full Ingestion Pipeline
Goal: PDF, DOCX, HTML, web scraping support

Backend: PDF parser (pypdf/pdfplumber), DOCX parser (python-docx), HTML parser, web fetcher
Test: Upload PDF → search works → wiki updated

**Acceptance:** All 5 document types work, metadata extracted correctly

### Iteration 11 — Frontend (Streamlit MVP)
Goal: Chat UI, document upload, wiki browser, memory viewer, admin dashboard

Frontend: Streamlit app with 5 pages
Test: Full workflow via UI: upload → ask → see answer → browse wiki

**Acceptance:** Non-technical user can upload and query documents

### Iteration 12 — Observability & Scale
Goal: Metrics, structured logs, performance optimization

Backend: prometheus-client metrics, structlog, query tracing
Infra: metrics endpoints, log rotation, performance benchmarks
Test: `/metrics` returns prometheus format, benchmark queries under 5s

**Acceptance:** Query latency < 5s p95, all metrics endpoints respond

---

## Future (Phase 6+)

- [ ] Qdrant migration (repository abstraction ready from day 1)
- [ ] Neo4j Knowledge Graph
- [ ] Distributed agents (multi-node)
- [ ] Multi-tenant SaaS deployment
- [ ] Headroom context compression
