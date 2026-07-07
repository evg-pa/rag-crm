"""Search REST endpoints.

GET /search?q=<string>&top_k=10          — semantic search
GET /search/hybrid?q=<string>&top_k=10   — hybrid (semantic + BM25 + reranker)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session
from app.retrieval.embeddings import EmbeddingModel, get_embedding_model
from app.retrieval.hybrid import DEFAULT_BM25_WEIGHT, DEFAULT_SEMANTIC_WEIGHT, hybrid_search
from app.retrieval.keyword import BM25Index
from app.retrieval.reranker import Reranker
from app.retrieval.semantic import semantic_search
from app.retrieval.vector_store import get_vector_store

router = APIRouter(prefix="/search", tags=["search"])

# ── Pydantic schemas ────────────────────────────────────────────────────────


class SearchResult(BaseModel):
    """A single semantic search result chunk."""

    id: str
    content: str
    document_id: str
    chunk_index: int
    similarity: float


class SearchResponse(BaseModel):
    """Response for GET /search."""

    query: str
    results: list[SearchResult] = Field(default_factory=list)


class HybridSearchResult(BaseModel):
    """A single hybrid search result chunk with all scores."""

    id: str
    content: str
    document_id: str
    chunk_index: int
    similarity: float
    bm25_score: float
    hybrid_score: float
    reranker_score: float | None = None


class HybridSearchResponse(BaseModel):
    """Response for GET /search/hybrid."""

    query: str
    results: list[HybridSearchResult] = Field(default_factory=list)


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="Search query text", min_length=1),
    top_k: int = Query(10, ge=1, le=100, description="Number of results to return"),
    db: AsyncSession = Depends(get_db_session),
    model: EmbeddingModel = Depends(get_embedding_model),
) -> Any:
    """Semantic search by embedding similarity.

    Encodes the query string with BGE-Small ONNX, then finds the top-k
    chunks by cosine distance via pgvector.
    """
    # Generate query embedding
    query_embedding = await model.embed(q)

    # Search via vector store (pgvector or Qdrant depending on config)
    vector_store = get_vector_store()
    results = await semantic_search(db, query_embedding, top_k=top_k, vector_store=vector_store)

    return SearchResponse(
        query=q,
        results=[SearchResult(**r) for r in results],
    )


@router.get("/hybrid", response_model=HybridSearchResponse)
async def search_hybrid(
    q: str = Query(..., description="Search query text", min_length=1),
    top_k: int = Query(10, ge=1, le=100, description="Number of results to return"),
    semantic_weight: float = Query(
        DEFAULT_SEMANTIC_WEIGHT,
        ge=0.0,
        le=1.0,
        description="Weight for semantic score in fusion",
    ),
    bm25_weight: float = Query(
        DEFAULT_BM25_WEIGHT,
        ge=0.0,
        le=1.0,
        description="Weight for BM25 score in fusion",
    ),
    db: AsyncSession = Depends(get_db_session),
    model: EmbeddingModel = Depends(get_embedding_model),
) -> Any:
    """Hybrid search: semantic + BM25 keyword, fused and re-ranked.

    Pipeline:
    1. Semantic search via pgvector (top-k × 3 for good recall)
    2. BM25 keyword search (top-k × 3 for good recall)
    3. Min-max normalize + weighted fusion
    4. BGE-Reranker cross-encoder re-ranking
    5. Return top-k final results
    """
    from app.retrieval.hybrid import _validate_weights

    try:
        _validate_weights(semantic_weight, bm25_weight)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None

    # Fetch more candidates than needed for better fusion recall
    candidate_k = max(top_k * 3, 100)

    # 1. Semantic search
    query_embedding = await model.embed(q)
    vector_store = get_vector_store()
    semantic_results = await semantic_search(
        db, query_embedding, top_k=candidate_k, vector_store=vector_store
    )

    # 2. BM25 keyword search
    bm25_results = await BM25Index.search(q, top_k=candidate_k, db=db)

    # 3. Fusion
    logger = __import__("logging").getLogger(__name__)
    logger.info(
        "hybrid search for %r: semantic=%d bm25=%d loaded=%s index=%s meta=%d",
        q,
        len(semantic_results),
        len(bm25_results),
        BM25Index.is_loaded(),
        "yes" if BM25Index._index is not None else "no",
        len(BM25Index._chunk_metadata) if BM25Index._chunk_metadata else 0,
    )
    fused = await hybrid_search(
        semantic_results=semantic_results,
        bm25_results=bm25_results,
        top_k=min(candidate_k, 50),  # limit for reranker budget
        semantic_weight=semantic_weight,
        bm25_weight=bm25_weight,
    )

    # 4. Re-rank
    reranker = Reranker()
    reranked = await reranker.rerank(q, fused, top_k=top_k)

    return HybridSearchResponse(
        query=q,
        results=[HybridSearchResult(**r) for r in reranked],
    )
