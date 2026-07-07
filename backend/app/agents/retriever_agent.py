"""RetrieverAgent — executes the chosen search strategy.

Delegates to the existing retrieval services (semantic.py, keyword.py,
hybrid.py) based on the query_type set by the RouterAgent.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import re

from app.agents.state import AgentState
from app.retrieval.embeddings import EmbeddingModel
from app.retrieval.hybrid import hybrid_search
from app.retrieval.keyword import BM25Index
from app.retrieval.semantic import semantic_search
from app.retrieval.vector_store import get_vector_store

# Number of candidates to retrieve before fusion/re-ranking
# Higher = better recall for exact matches (BM25), lower = faster
_CANDIDATE_K = 100


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
    """Run hybrid (semantic + BM25 fusion) search.

    Also searches extracted date/number patterns as a pure BM25 query
    to ensure exact keyword hits (e.g., ``2026.06.30``) survive the
    English-only semantic and reranker stages.
    """
    query_embedding = await model.embed(query)
    vector_store = get_vector_store()
    semantic_results = await semantic_search(
        db, query_embedding, top_k=_CANDIDATE_K, vector_store=vector_store
    )
    bm25_results = await BM25Index.search(query, top_k=_CANDIDATE_K, db=db)

    # ── Keyword-only BM25 pass for dates/numbers ──────────────────────
    # Extract date-like and number-like tokens for exact-match retrieval
    keyword_tokens: list[str] = re.findall(
        r"\b\d{2,4}[-./]\d{1,2}[-./]\d{2,4}\b|\b\d{2,4}[-./]\d{1,2}\b", query
    )
    if keyword_tokens:
        kw_query = " ".join(keyword_tokens)
        kw_results = await BM25Index.search(kw_query, top_k=_CANDIDATE_K, db=db)
        # Merge BM25 results: deduplicate by id, keep the one with higher score
        existing_ids = {r["id"] for r in bm25_results}
        for kr in kw_results:
            if kr["id"] not in existing_ids:
                bm25_results.append(kr)
                existing_ids.add(kr["id"])
            else:
                for existing in bm25_results:
                    if existing["id"] == kr["id"]:
                        existing["bm25_score"] = max(
                            existing.get("bm25_score", 0.0) or 0.0,
                            kr.get("bm25_score", 0.0) or 0.0,
                        )
                        break

    fused = await hybrid_search(
        semantic_results=semantic_results,
        bm25_results=bm25_results,
        top_k=_CANDIDATE_K,
    )

    # ── Preserve BM25-only winners dropped by hybrid top-K ────────────
    # Chunks that only matched BM25 (no semantic hit) often get a low
    # hybrid score and fall outside the top-K cutoff.  We inject any
    # such chunk with bm25_score > 0 that wasn't already included.
    fused_ids = {r["id"] for r in fused}
    bm25_only_survivors: list[dict[str, Any]] = []
    for r in bm25_results:
        if r["id"] not in fused_ids and (r.get("bm25_score", 0.0) or 0.0) > 0:
            r["similarity"] = 0.0
            r["hybrid_score"] = round(
                (0.5 * 0.0 + 0.5 * _min_max_normalize_single(r["bm25_score"], bm25_results))
                / 1.0,
                6,
            )
            bm25_only_survivors.append(r)

    # ── Also promote high-BM25 chunks that ARE in the fused results    ──
    # These are often buried below the top-30 cutoff because their
    # semantic score is zero; prepend them so the answer agent sees them.
    bm25_in_fused: list[dict[str, Any]] = []
    for r in bm25_results:
        score = r.get("bm25_score", 0.0) or 0.0
        if score > 0 and r["id"] in fused_ids:
            # Find the fused entry and move it to the front
            for f in fused:
                if f["id"] == r["id"] and f["similarity"] == 0.0:
                    bm25_in_fused.append(f)
                    break

    return bm25_only_survivors + bm25_in_fused + [f for f in fused if f not in bm25_in_fused]


def _min_max_normalize_single(value: float, all_results: list[dict[str, Any]]) -> float:
    """Normalize a single BM25 score using the min-max of all results."""
    scores = [float(r.get("bm25_score", 0.0) or 0.0) for r in all_results]
    if not scores:
        return 0.0
    mn, mx = min(scores), max(scores)
    if mx == mn:
        return 1.0 if value > 0 else 0.0
    return (value - mn) / (mx - mn)


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
