# Iteration 13+ Roadmap — RAG-CRM: Phase 6

> **Goal:** Complete the RAG + CRM integration, then productionize.
> Based on the completed docs/roadmap.md Phases 1-5 (Iterations 1-12 done).

---

## Current State (Iterations 1-12 — 100% Complete)

| Area | Status |
|---|---|
| Core infra (FastAPI, PostgreSQL+pgvector, Redis, Docker) | ✅ |
| Document Ingestion (.md, .txt, .pdf, .docx, .html, web scrape) | ✅ |
| Embeddings (BGE-Small ONNX) + Semantic Search | ✅ |
| BM25 Keyword + Hybrid Search + Reranker | ✅ |
| 7-Agent LangGraph Pipeline (Router→Retriever→Reranker→Answer→Critic→Memory→Synthesizer) | ✅ |
| Knowledge Agent + LLM Wiki | ✅ |
| Memory System (Working, Episodic, Semantic, Procedural) | ✅ |
| Streamlit Frontend (6 pages: upload, chat, wiki, memory, admin, status) | ✅ |
| Observability (health probes, Prometheus metrics, structured logging, rate limiting) | ✅ |
| JWT Multi-User Auth (register, login, refresh, document ownership) | ✅ |
| Tests: **212 passed, 0 failed** | ✅ |

---

## Phase 6: CRM Integration (Iterations 13-15)

### Iteration 13 — CRM Data Connector

**Goal:** Connect to an external CRM API, pull contacts/deals, and index them into the RAG pipeline.

**What to build:**
- CRM connector module (`app/connectors/crm.py`) with pluggable adapter pattern
- A simple REST CRM adapter (`app/connectors/adapters/rest.py`) — talks to any REST-based CRM
- CRM sync endpoint (`POST /connectors/crm/sync`) — triggers full re-index
- Background scheduler for periodic sync (cron-based, configurable interval)
- Ingest CRM contacts/deals as documents (JSON → text → chunks → embeddings)
- Add `source: "crm"` tag to distinguish from uploaded documents

**Key decisions:**
- Use `httpx.AsyncClient` for CRM API calls
- Store CRM API credentials as environment variables (not in DB)
- CRM data maps to the existing Document+Chunk schema (no new tables needed)
- Each CRM entity (contact, deal, activity) becomes one document

**Files to create:**
- `backend/app/connectors/__init__.py`
- `backend/app/connectors/crm.py` — connector orchestrator
- `backend/app/connectors/adapters/__init__.py`
- `backend/app/connectors/adapters/rest.py` — REST CRM adapter
- `backend/app/api/connectors.py` — connector API endpoints
- `backend/tests/test_crm_connector.py` — unit + integration tests

**Acceptance:**
- `POST /connectors/crm/sync` returns 202 and ingests CRM data
- CRM documents appear in search results with `source: "crm"` tag
- All 212 existing tests still pass

---

### Iteration 14 — CRM Query & Context Enrichment

**Goal:** Allow natural-language questions about CRM data with enriched context.

**What to build:**
- CRM-aware query routing: if query mentions CRM entities → route to CRM-aware retriever
- CRM entity extraction: extract contact/deal/company names from queries
- Cross-reference CRM data with documents (e.g. "what deals relate to this PDF?")
- CRM context injection into the 7-agent LangGraph pipeline
- Preset CRM queries (top deals, recent activities, etc.) as quick-buttons

**Key decisions:**
- Use the existing LangGraph pipeline; add a CRM context node
- CRM entity extraction via simple regex + fuzzy matching (no separate NER model needed)
- Cross-referencing via shared keywords between CRM records and document chunks

**Files to modify:**
- `backend/app/agents/state_graph.py` — add CRM context node
- `backend/app/agents/crm_context.py` — new agent for CRM enrichment
- `backend/app/api/qa.py` — add CRM quick-query presets
- `backend/tests/test_crm_qa.py` — CRM-specific Q&A tests

**Acceptance:**
- "Show me deals related to the contract document" returns correct CRM entities
- CRM quick-queries return formatted CRM data
- All existing tests pass

---

### Iteration 15 — CRM Frontend Dashboard

**Goal:** Add CRM data visualization to the Streamlit frontend.

**What to build:**
- CRM dashboard page: synced contacts, deals, and their RAG-derived insights
- CRM data browser: filter/search CRM entities ingested into RAG
- Sync status indicator: last sync time, records ingested, errors
- Trigger sync button (manual re-index)
- Quick CRM query panel for natural-language CRM questions

**Files to modify:**
- `frontend/app.py` — add CRM pages to navigation
- `frontend/pages/crm_dashboard.py` — CRM overview
- `frontend/pages/crm_search.py` — CRM-specific search
- `frontend/components/crm_sync_status.py` — sync widget

**Acceptance:**
- CRM dashboard loads with real data after sync
- Manual sync triggers from UI
- Quick queries return formatted results
- Existing Streamlit pages unaffected

---

## Phase 7: Production Readiness (Iterations 16-17)

### Iteration 16 — Deployment & CI/CD

**Goal:** Push-button deployment with CI/CD pipeline.

**What to build:**
- GitHub Actions CI: lint → test → build → deploy
- Docker Compose production override (resource limits, restart policies, secrets)
- HTTPS with Let's Encrypt + nginx reverse proxy
- Healthcheck integration with monitoring (Uptime Kuma or similar)
- Backup strategy for PostgreSQL volumes

**Acceptance:**
- `git push` triggers CI that runs tests and builds
- Production compose starts with HTTPS
- Backups work (create + restore tested)

---

### Iteration 17 — Performance & Hardening

**Goal:** Production-hardened RAG with benchmarks.

**What to build:**
- Query latency benchmarks (p50/p95/p99 under realistic load)
- Connection pooling optimization (SQLAlchemy pools, Redis pools)
- Embedding model caching (ONNX session caching)
- Document upload size limits + streaming validation
- Error rate alerts (Prometheus + alert rules)
- Rate limit refinement (per-route tiers, burst allowance)

**Acceptance:**
- P95 query latency under 5s with 50 concurrent users
- No memory leaks under sustained load (2h+ stress test)
- All security checks pass (no hardcoded secrets, no injection vectors)

---

## Phase 8: Advanced (Iterations 18-19)

### Iteration 18 — Qdrant Migration

**Goal:** Replace pgvector with Qdrant for better performance and scalability.

**What to build:**
- Vector repository abstraction (already hinted in roadmap)
- Qdrant adapter implementation
- Migration script to copy pgvector data to Qdrant
- Feature flag to switch between pgvector/Qdrant at runtime

**Acceptance:**
- Qdrant-backed search returns identical results to pgvector (within rounding)
- Migration script moves 1000+ vectors without data loss

---

### Iteration 19 — Knowledge Graph (Neo4j)

**Goal:** Extract entities and relationships from documents into a knowledge graph.

**What to build:**
- Neo4j connector (Docker Compose service)
- Entity extraction pipeline (LLM-based, batch process on ingestion)
- Relationship extraction (connects entities by co-occurrence and LLM inference)
- Graph-enhanced search (expand queries with related entities)
- Graph visualization in Streamlit frontend

**Acceptance:**
- Ingested documents produce entity nodes and relationship edges
- Graph-enhanced search returns results that pure vector search misses
- Graph visualization renders entities and their connections

---

## Phase 9: Future (Post-Roadmap)

- Multi-tenant SaaS isolation (per-org data separation)
- Agent web browsing (Paperclip-style) for live data enrichment
- Voice interface (text-to-speech on answers, speech-to-text input)
- Multi-language document support
- Federated search (query multiple RAG instances)

---

## Open Questions

1. **Which CRM to integrate with?** — HubSpot (most common) vs. custom REST API vs. Salesforce. Affects adapter complexity.
2. **Sync frequency?** — Daily vs. real-time webhooks. Webhooks preferred for freshness but add complexity.
3. **Self-hosted vs. cloud Neo4j?** — Docker Compose for dev, cloud for prod. Affects Iteration 19 cost.
4. **Qdrant urgency?** — pgvector works fine for <100K vectors. Qdrant only needed at scale.
