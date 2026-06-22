"""Q&A REST endpoints.

POST /qa              — answer a question using hybrid search + LLM
GET  /qa/history      — stub for QA history (not yet implemented)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_db_session, get_settings
from app.retrieval.embeddings import EmbeddingModel, get_embedding_model
from app.retrieval.hybrid import hybrid_search
from app.retrieval.keyword import BM25Index
from app.retrieval.qa import AnswerAgent, AnswerResult
from app.retrieval.reranker import Reranker
from app.retrieval.semantic import semantic_search

router = APIRouter(prefix="/qa", tags=["qa"])

# ── Pydantic schemas ────────────────────────────────────────────────────────


class QARequest(BaseModel):
    """Request body for POST /qa."""

    query: str = Field(..., description="The question to answer", min_length=1)
    top_k: int = Field(10, ge=1, le=100, description="Number of chunks to retrieve")


class QAHistoryResponse(BaseModel):
    """Stub response for GET /qa/history."""

    items: list[dict[str, Any]] = Field(default_factory=list)


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("", response_model=AnswerResult)
async def ask_question(
    body: QARequest,
    db: AsyncSession = Depends(get_db_session),
    model: EmbeddingModel = Depends(get_embedding_model),
    settings: Settings = Depends(get_settings),
) -> AnswerResult:
    """Answer a question using hybrid search + LLM generation.

    Pipeline:
    1. Hybrid search (semantic + BM25 + reranker) for relevant chunks.
    2. LLM (DeepSeek or Ollama fallback) generates a cited answer.
    3. Returns answer text, citations, and confidence score.

    If no chunks are found, returns a graceful empty response.
    """
    # ── 1. Hybrid search ────────────────────────────────────────────────
    candidate_k = max(body.top_k * 3, 30)

    # Semantic search
    query_embedding = await model.embed(body.query)
    semantic_results = await semantic_search(db, query_embedding, top_k=candidate_k)

    # BM25 keyword search
    bm25_results = await BM25Index.search(body.query, top_k=candidate_k, db=db)

    # Fusion
    fused = await hybrid_search(
        semantic_results=semantic_results,
        bm25_results=bm25_results,
        top_k=min(candidate_k, 50),
    )

    # Re-rank
    reranker = Reranker()
    reranked = await reranker.rerank(body.query, fused, top_k=body.top_k)

    # ── 2. LLM answer generation ────────────────────────────────────────
    agent = AnswerAgent(settings=settings)
    try:
        result = await agent.answer(
            query=body.query,
            chunks=reranked,
            top_k=body.top_k,
        )
    finally:
        await agent.close()

    return result


@router.get("/history", response_model=QAHistoryResponse)
async def qa_history(
    settings: Settings = Depends(get_settings),
) -> QAHistoryResponse:
    """Return QA query history (stub — not yet implemented)."""
    return QAHistoryResponse(items=[])
