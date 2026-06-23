"""Q&A REST endpoints — powered by the 7-agent LangGraph pipeline.

POST /qa              — answer a question using the full LangGraph pipeline
GET  /qa/history      — stub for QA history (not yet implemented)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.agents.state_graph import build_qa_graph
from app.core.config import Settings
from app.core.dependencies import get_db_session, get_settings
from app.retrieval.embeddings import EmbeddingModel, get_embedding_model
from app.retrieval.qa import AnswerResult, Citation

router = APIRouter(prefix="/qa", tags=["qa"])

# ── Compiled graph (lazy, built once) ────────────────────────────────────────
_qa_graph: Any = None  # compiled LangGraph StateGraph


def _get_graph() -> Any:
    """Return (or lazily build) the compiled LangGraph QA pipeline."""
    global _qa_graph
    if _qa_graph is None:
        _qa_graph = build_qa_graph()
    return _qa_graph


# ── Pydantic schemas ────────────────────────────────────────────────────────


class QARequest(BaseModel):
    """Request body for POST /qa."""

    query: str = Field(..., description="The question to answer", min_length=1)
    top_k: int = Field(10, ge=1, le=100, description="Number of chunks to retrieve")
    session_id: str = Field("default", description="Session identifier for conversation memory")


class QAResponse(BaseModel):
    """Response body for POST /qa (LangGraph pipeline output)."""

    answer_text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence_score: float = 0.0
    final_response: str = ""
    query_type: str = ""


class QAHistoryResponse(BaseModel):
    """Stub response for GET /qa/history."""

    items: list[dict[str, Any]] = Field(default_factory=list)


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("", response_model=QAResponse)
async def ask_question(
    body: QARequest,
    db: AsyncSession = Depends(get_db_session),
    model: EmbeddingModel = Depends(get_embedding_model),
    settings: Settings = Depends(get_settings),
) -> QAResponse:
    """Answer a question using the 7-agent LangGraph pipeline.

    Pipeline:
    1. RouterAgent — classifies the query type
    2. RetrieverAgent — runs the appropriate search strategy
    3. RerankerAgent — re-ranks top results
    4. AnswerAgent — generates an answer via DeepSeek / Ollama
    5. CriticAgent — validates the answer (up to 2 retries)
    6. MemoryAgent — stores the exchange in session history
    7. SynthesizerAgent — produces the final polished response
    """
    # Build initial state with injected dependencies
    initial_state: AgentState = {
        "query": body.query,
        "session_id": body.session_id,
        "top_k": body.top_k,
        "_db_session": db,           # type: ignore[typeddict-item]
        "_embedding_model": model,   # type: ignore[typeddict-item]
        "_settings": settings,       # type: ignore[typeddict-item]
    }

    graph = _get_graph()

    # FIX 6: wrap graph.ainvoke() in try/except for meaningful error responses
    try:
        raw_state: dict[str, Any] = await graph.ainvoke(initial_state)  # type: ignore[assignment]
    except Exception as exc:
        return QAResponse(
            answer_text=f"Pipeline error: {exc}",
            citations=[],
            confidence_score=0.0,
            final_response=f"An error occurred while processing your question: {exc}",
            query_type="",
        )

    # FIX 4: strip DI-injected private fields before any serialization
    raw_state.pop("_db_session", None)
    raw_state.pop("_embedding_model", None)
    raw_state.pop("_settings", None)

    result_state: AgentState = raw_state  # type: ignore[assignment]

    # Extract fields from the final state
    answer_text: str = result_state.get("answer_text", "")
    citations_raw: list[dict[str, Any]] = result_state.get("citations", [])
    confidence_score: float = float(result_state.get("confidence_score", 0.0))
    final_response: str = result_state.get("final_response", answer_text)
    query_type: str = result_state.get("query_type", "")

    # Convert citation dicts to Citation models
    citations: list[Citation] = []
    for cit in citations_raw:
        citations.append(
            Citation(
                chunk_id=str(cit.get("chunk_id", "")),
                document_id=str(cit.get("document_id", "")),
                content_snippet=str(cit.get("content_snippet", "")),
            )
        )

    return QAResponse(
        answer_text=answer_text,
        citations=citations,
        confidence_score=confidence_score,
        final_response=final_response,
        query_type=query_type,
    )


@router.get("/history", response_model=QAHistoryResponse)
async def qa_history(
    settings: Settings = Depends(get_settings),
) -> QAHistoryResponse:
    """Return QA query history (stub — not yet implemented)."""
    return QAHistoryResponse(items=[])
