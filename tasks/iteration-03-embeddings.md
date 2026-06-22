# Iteration 3 — Paperclip Task

## Goal
Add semantic search: generate embeddings for document chunks via BGE-Small ONNX, store in pgvector, provide search endpoint.

## Acceptance Criteria

1. `GET /search?q=query` returns ranked chunks by semantic similarity
2. Embeddings generated using BGE-Small-en-v1.5 (ONNX for CPU speed)
3. pgvector column (`embedding vector(384)`) on chunks table
4. Alembic migration adds the vector column
5. Test: upload doc about "payments" → search "payment methods" → relevant chunk in top-3
6. ruff + mypy --strict pass
7. All previous tests still pass

## Files to Create/Update

### UPDATE: backend/app/models/chunk.py
Add `embedding: Mapped[Vector] = mapped_column(Vector(384), nullable=True)`

### UPDATE: alembic migration
New migration: "add embedding vector to chunks"

### NEW: backend/app/retrieval/__init__.py

### NEW: backend/app/retrieval/embeddings.py
- `class EmbeddingService`
- Load BGE-Small ONNX model (use `sentence-transformers` with `onnxruntime`)
- `async def embed(text: str) -> list[float]`
- `async def embed_batch(texts: list[str]) -> list[list[float]]`
- Lazy loading (model loads on first call, not at import)
- Fallback: if ONNX not available, use pure PyTorch BGE-Small

### NEW: backend/app/retrieval/semantic.py
- `async def semantic_search(query: str, db: AsyncSession, limit: int = 10) -> list[Chunk]`
- Uses pgvector `<=>` (cosine distance) operator
- Returns chunks ordered by similarity

### NEW: backend/app/api/search.py
- `GET /search?q=query&limit=10`
- Returns: `[{chunk_id, document_id, content, filename, similarity}, ...]`

### UPDATE: backend/app/api/__init__.py
Add search router.

### UPDATE: backend/pyproject.toml
Add: `sentence-transformers`, `onnxruntime`, `pgvector` (Python package)

### UPDATE: backend/Dockerfile
Add: `sentence-transformers`, `onnxruntime`, `pgvector`

### NEW: backend/tests/test_search.py
Tests (can mock embedding model to avoid 2GB download in CI):
- `test_semantic_search_returns_results`
- `test_search_endpoint_returns_200`

## Constraints
- Model downloads on first use (~30MB for ONNX quantized)
- pgvector extension must be enabled (already in init-db.sql)
- Cosine distance (<=>) for similarity

## Directory
/media/sf_VM_Share/Projects/AI/rag-crm/

## Coordination
1. CEO → subtasks
2. Coder(s) → implement
3. QA → verify: semantic search returns relevant results, pytest, ruff, mypy
