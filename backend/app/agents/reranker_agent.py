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

    BM25 preservation: any chunk with BM25_score > 0 that falls outside
    the top-K after re-ranking is injected back at the end, because the
    English-only cross-encoder penalises non-English content and can
    suppress exact BM25 keyword hits.
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

    # ── BM25 preservation: inject BM25 winners that the reranker dropped ──
    top_k = min(len(chunks), MAX_RERANK_CANDIDATES)
    reranked_ids = {c.get("id", "") for c in reranked}
    preserved: list[dict[str, Any]] = list(reranked)

    for c in chunks:
        cid = c.get("id", "")
        bm25 = c.get("bm25_score", 0.0) or 0.0
        if cid not in reranked_ids and bm25 > 0:
            if "reranker_score" not in c:
                c["reranker_score"] = 0.0
            preserved.append(c)

    if len(preserved) > top_k:
        preserved = preserved[:top_k]

    return {
        "reranked_chunks": preserved,
        "agent_states": {
            **(state.get("agent_states") or {}),
            "reranker": "completed",
        },
    }
