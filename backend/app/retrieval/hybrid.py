"""Hybrid search: fuse semantic and BM25 results with weighted scoring.

Semantic scores are similarity values (0..1 from cosine similarity).
BM25 scores are unbounded non-negative floats.  Both are min-max
normalized before weighted fusion so that neither source dominates.
"""

from __future__ import annotations

from typing import Any

# ── Default fusion weights ──────────────────────────────────────────────────
DEFAULT_SEMANTIC_WEIGHT: float = 0.5
DEFAULT_BM25_WEIGHT: float = 0.5


def _validate_weights(semantic_weight: float, bm25_weight: float) -> None:
    """Raise ValueError for invalid weight values."""
    if not (0.0 <= semantic_weight <= 1.0):
        raise ValueError(f"semantic_weight must be in [0, 1], got {semantic_weight}")
    if not (0.0 <= bm25_weight <= 1.0):
        raise ValueError(f"bm25_weight must be in [0, 1], got {bm25_weight}")
    total = semantic_weight + bm25_weight
    if total <= 0:
        raise ValueError("At least one weight must be positive.")


def _min_max_normalize(scores: list[float]) -> list[float]:
    """Min-max normalize a list of scores to [0, 1].

    If all scores are identical (min == max), returns 1.0 for every
    positive-scored item and 0.0 otherwise.
    """
    if not scores:
        return []
    mn = min(scores)
    mx = max(scores)
    if mx == mn:
        return [1.0 if s > 0 else 0.0 for s in scores]
    return [(s - mn) / (mx - mn) for s in scores]


async def hybrid_search(
    semantic_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
    top_k: int = 10,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
) -> list[dict[str, Any]]:
    """Fuse semantic and BM25 results with weighted scoring.

    Parameters
    ----------
    semantic_results:
        List of dicts from ``semantic_search()``, each with at least
        ``id`` and ``similarity``.
    bm25_results:
        List of dicts from ``BM25Index.search()``, each with at least
        ``id`` and ``bm25_score``.
    top_k:
        Number of results to return after fusion.
    semantic_weight:
        Weight for the semantic score in the fusion (default 0.5).
    bm25_weight:
        Weight for the BM25 score in the fusion (default 0.5).

    Returns
    -------
    list[dict]
        Fused results ordered by descending ``hybrid_score``.  Each dict
        contains ``id``, ``content``, ``document_id``, ``chunk_index``,
        ``similarity``, ``bm25_score``, and ``hybrid_score``.
    """
    _validate_weights(semantic_weight, bm25_weight)

    total_weight = semantic_weight + bm25_weight

    # Build lookup maps by chunk id
    semantic_by_id: dict[str, dict[str, Any]] = {r["id"]: r for r in semantic_results}
    bm25_by_id: dict[str, dict[str, Any]] = {r["id"]: r for r in bm25_results}

    # Collect all unique chunk ids from both result sets
    all_ids: set[str] = set(semantic_by_id.keys()) | set(bm25_by_id.keys())

    if not all_ids:
        return []

    # Extract raw scores for normalization
    ids_in_order: list[str] = list(all_ids)
    raw_semantic: list[float] = [
        semantic_by_id.get(cid, {}).get("similarity", 0.0) for cid in ids_in_order
    ]
    raw_bm25: list[float] = [
        bm25_by_id.get(cid, {}).get("bm25_score", 0.0) for cid in ids_in_order
    ]

    norm_semantic = _min_max_normalize(raw_semantic)
    norm_bm25 = _min_max_normalize(raw_bm25)

    # Fuse scores
    fused: list[dict[str, Any]] = []
    for i, cid in enumerate(ids_in_order):
        hybrid = (
            semantic_weight * norm_semantic[i] + bm25_weight * norm_bm25[i]
        ) / total_weight

        # Prefer semantic result metadata when available (more complete),
        # fall back to BM25 metadata
        base = semantic_by_id.get(cid) or bm25_by_id.get(cid) or {}
        fused.append(
            {
                "id": cid,
                "content": base.get("content", ""),
                "document_id": base.get("document_id", ""),
                "chunk_index": base.get("chunk_index", -1),
                "similarity": semantic_by_id.get(cid, {}).get("similarity", 0.0),
                "bm25_score": bm25_by_id.get(cid, {}).get("bm25_score", 0.0),
                "hybrid_score": round(hybrid, 6),
            }
        )

    # Sort descending by hybrid score, then take top_k
    fused.sort(key=lambda r: r["hybrid_score"], reverse=True)
    return fused[:top_k]
