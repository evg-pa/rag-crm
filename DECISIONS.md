# DECISIONS — RAG-CRM

> Persistent decision log. Read by Paperclip agents at session start.
> Each entry: date | problem | decision | rationale | affected files.

---

## 2026-06-17: Project initialization

- **Problem:** New RAG project needs architecture decisions for local-first, incremental development
- **Decision:**
  - pgvector as primary vector store (Qdrant migration path via repository abstraction)
  - rank_bm25 for true BM25 (not PostgreSQL tsvector which is TF/IDF)
  - BGE-Small ONNX for CPU-only environment (upgrade to BGE-M3 ONNX when GPU available)
  - Simple state machine for early iterations, migrate to LangGraph at Iteration 7
  - DeepSeek API primary LLM, Ollama local LLM as fallback from day 1
  - Streamlit MVP (Iteration 11), Next.js final (Iteration 12+)
  - Temperature 0 for all factual/retrieval steps
- **Files:** MAP.md, docs/architecture.md, infrastructure/docker-compose.yml

---

## 2026-06-18: Iteration 1 ACCEPTED — Core Infrastructure

- **Completed by:** Paperclip agents (CEO → CTO → Coder)
- **Verification:**
  - ruff: 0 errors ✅
  - ruff format: 11 files formatted ✅
  - mypy --strict: 0 errors ✅
  - pytest: 4/4 passed ✅
  - `docker compose up --build`: all 3 services healthy ✅
  - `GET /health`: `{"status":"ok","version":"0.1.0","database":"connected"}` ✅
  - `GET /health/live`: `{"status":"alive"}` ✅
  - `GET /`: redirect to `/docs` ✅
- **Fixes applied by Hermes:** Dockerfile → multi-stage, mypy strict fixes (test type annotations, unused type:ignore removed)
- **Status:** ACCEPT ✅ — proceed to Iteration 2

---

## 2026-06-17: Three witnesses rule adopted

- **Source:** Habr article 1046586 (QualityLab)
- **Decision:** Every generated answer must be verified by ≥2 independent methods.
  Answer Agent produces response → Critic Agent validates blindly → Python oracle checks intermediate steps
- **Files:** CLAUDE.md, backend/app/agents/critic_agent.py

---

## 2026-06-17: Anchor test strategy

- **Source:** Habr article 1046586
- **Decision:** 5-10 known-ground-truth queries maintained in `tests/anchors/`. Complete pipeline
  must pass all anchors before any new feature is accepted.
- **Files:** docs/roadmap.md, tests/anchors/

---

## 2026-06-17: Hierarchical context structure

- **Source:** Habr article 1024878 (Creatman)
- **Decision:** Three-level context system for all agents:
  Level 0 = MAP.md (workspace map, always in context)
  Level 1 = CLAUDE.md (project architecture, loaded on demand)
  Level 2 = Source code (only when needed)
- **Files:** MAP.md, CLAUDE.md
