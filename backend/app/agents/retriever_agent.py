"""RetrieverAgent — executes the chosen search strategy.

Delegates to the existing retrieval services (semantic.py, keyword.py,
hybrid.py) based on the query_type set by the RouterAgent.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.retrieval.embeddings import EmbeddingModel
from app.retrieval.hybrid import hybrid_search
from app.retrieval.keyword import BM25Index
from app.retrieval.semantic import semantic_search
from app.retrieval.vector_store import get_vector_store

# Number of candidates to retrieve before fusion/re-ranking
_CANDIDATE_K = 30


async def _run_semantic(
    db: AsyncSession,
    model: EmbeddingModel,
    query: str,
) -> list[dict[str, Any]]:
    """Run semantic (vector) search."""
    query_embedding = await model.embed(query)
    vector_store = get_vector_store()
    return await semantic_search(db, query_embedding, top_k=_CANDIDATE_K, vector_store=vector_store)


async def _run_keyword(
    db: AsyncSession,
    query: str,
) -> list[dict[str, Any]]:
    """Run BM25 keyword search."""
    return await BM25Index.search(query, top_k=_CANDIDATE_K, db=db)


async def _run_hybrid(
    db: AsyncSession,
    model: EmbeddingModel,
    query: str,
) -> list[dict[str, Any]]:
    """Run hybrid (semantic + BM25 fusion) search."""
    query_embedding = await model.embed(query)
    vector_store = get_vector_store()
    semantic_results = await semantic_search(
        db, query_embedding, top_k=_CANDIDATE_K, vector_store=vector_store
    )
    bm25_results = await BM25Index.search(query, top_k=_CANDIDATE_K, db=db)
    return await hybrid_search(
        semantic_results=semantic_results,
        bm25_results=bm25_results,
        top_k=_CANDIDATE_K,
    )


async def retriever_agent(state: AgentState) -> dict:
    """LangGraph node: run the retrieval strategy dictated by query_type.

    Expects the following keys to be present in *state*:
      - ``query``
      - ``query_type``
      - ``_db_session`` — an active ``AsyncSession``
      - ``_embedding_model`` — an ``EmbeddingModel`` instance

    Returns a dict with ``retrieved_chunks`` and an updated
    ``agent_states`` entry.
    """
    query: str = state.get("query", "")
    query_type: str = state.get("query_type", "hybrid")
    db: AsyncSession | None = state.get("_db_session")  # type: ignore[typeddict-item]
    model: EmbeddingModel | None = state.get("_embedding_model")  # type: ignore[typeddict-item]

    chunks: list[dict[str, Any]] = []

    if db is None:
        return {
            "retrieved_chunks": [],
            "error": "No database session available in state",
            "agent_states": {
                **(state.get("agent_states") or {}),
                "retriever": "error",
            },
        }

    try:
        if query_type == "semantic":
            if model is None:
                raise ValueError("EmbeddingModel not available for semantic search")
            chunks = await _run_semantic(db, model, query)
        elif query_type == "keyword":
            chunks = await _run_keyword(db, query)
        else:  # hybrid (default) or any unrecognised type
            if model is None:
                raise ValueError("EmbeddingModel not available for hybrid search")
            chunks = await _run_hybrid(db, model, query)
    except Exception as exc:
        return {
            "retrieved_chunks": [],
            "error": f"Retrieval failed: {exc}",
            "agent_states": {
                **(state.get("agent_states") or {}),
                "retriever": "error",
            },
        }

    return {
        "retrieved_chunks": chunks,
        "agent_states": {
            **(state.get("agent_states") or {}),
            "retriever": "completed",
        },
    }
