"""RerankerAgent — re-ranks top-20 retrieved chunks with BGE-Reranker.

Uses the cross-encoder from app.retrieval.reranker.  Falls back to the
original chunk order if the reranker model isn't loaded.
"""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState
from app.retrieval.reranker import MAX_RERANK_CANDIDATES, Reranker


async def reranker_agent(state: AgentState) -> dict:
    """LangGraph node: re-rank retrieved chunks using the BGE cross-encoder.

    Expects ``query`` and ``retrieved_chunks`` in *state*.  Returns
    ``reranked_chunks`` (each with an added ``reranker_score`` field)
    and an updated ``agent_states`` entry.
    """
    query: str = state.get("query", "")
    chunks: list[dict[str, Any]] = state.get("retrieved_chunks", [])

    if not chunks:
        return {
            "reranked_chunks": [],
            "agent_states": {
                **(state.get("agent_states") or {}),
                "reranker": "skipped",
            },
        }

    try:
        reranker = Reranker()
        reranked = await reranker.rerank(
            query=query,
            candidates=chunks,
            top_k=min(len(chunks), MAX_RERANK_CANDIDATES),
        )
    except Exception:
        # Model failed to load or inference error — keep original order
        reranked = chunks

    return {
        "reranked_chunks": reranked,
        "agent_states": {
            **(state.get("agent_states") or {}),
            "reranker": "completed",
        },
    }
