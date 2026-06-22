"""Semantic search REST endpoint.

GET /search?q=<string>&top_k=10
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db_session
from app.retrieval.embeddings import EmbeddingModel, get_embedding_model
from app.retrieval.semantic import semantic_search

router = APIRouter(prefix="/search", tags=["search"])

# ── Pydantic schemas ────────────────────────────────────────────────────────


class SearchResult(BaseModel):
    """A single search result chunk."""

    id: str
    content: str
    document_id: str
    chunk_index: int
    similarity: float


class SearchResponse(BaseModel):
    """Response for GET /search."""

    query: str
    results: list[SearchResult] = Field(default_factory=list)


# ── Endpoint ────────────────────────────────────────────────────────────────


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

    # Search pgvector
    results = await semantic_search(db, query_embedding, top_k=top_k)

    return SearchResponse(
        query=q,
        results=[SearchResult(**r) for r in results],
    )
