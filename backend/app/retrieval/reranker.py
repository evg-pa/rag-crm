"""BGE-Reranker cross-encoder for re-ranking search results.

Lazy-loads the BAAI/bge-reranker-v2-m3 model via HuggingFace transformers
on first use (not at import time).  Runs on CPU and is limited to 50
candidates for performance.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.dependencies import get_settings

# Re-rank at most this many candidates (CPU budget guard)
MAX_RERANK_CANDIDATES: int = 50


class Reranker:
    """Lazy-loading BGE-Reranker cross-encoder.

    Thread-safe: only one load per process, protected by asyncio.Lock
    so concurrent first-calls don't double-load.
    """

    _model: Any | None = None
    _tokenizer: Any | None = None
    _lock: asyncio.Lock | None = None
    _loaded: bool = False

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    def _ensure_loaded(cls) -> None:
        """Blocking load of the cross-encoder model and tokenizer.

        Called inside the async lock — must not be called directly from
        async context without the lock held.
        """
        if cls._loaded:
            return

        from transformers import (  # type: ignore[import-not-found,unused-ignore]
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        import torch  # type: ignore[import-not-found]

        settings = get_settings()
        model_name = settings.RERANKER_MODEL

        cls._tokenizer = AutoTokenizer.from_pretrained(model_name)
        cls._model = AutoModelForSequenceClassification.from_pretrained(
            model_name, torch_dtype=torch.float32
        )
        cls._loaded = True

    async def _load(self) -> None:
        """Async-safe lazy loader with timeout."""
        lock = self._get_lock()
        async with lock:
            if not self._loaded:
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(self._ensure_loaded), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    # Model not loaded — will fall back to un-reranked results
                    pass

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Re-rank candidates with a cross-encoder and return the top-k.

        Parameters
        ----------
        query:
            The search query string.
        candidates:
            List of result dicts to re-rank.  Each must have at least
            ``content``.  Limited to ``MAX_RERANK_CANDIDATES`` (50).
        top_k:
            Number of results to return after re-ranking.

        Returns
        -------
        list[dict]
            Re-ranked results, each with an added ``reranker_score`` field
            (the raw cross-encoder logit).
        """
        if not candidates:
            return []

        # Budget guard: only re-rank the first MAX_RERANK_CANDIDATES
        limited = candidates[:MAX_RERANK_CANDIDATES]

        if not self._loaded:
            await self._load()

        if not self._loaded:
            # Model failed to load — return candidates un-reranked
            return candidates[:top_k]

        scores = await asyncio.to_thread(self._rerank_sync, query, limited)

        # Pair scores with original candidates, sort descending, take top_k
        scored: list[tuple[float, dict[str, Any]]] = list(
            zip(scores, limited, strict=True)
        )
        scored.sort(key=lambda pair: pair[0], reverse=True)

        return [
            {
                **candidate,
                "reranker_score": round(float(score), 6),
            }
            for score, candidate in scored[:top_k]
        ]

    def _rerank_sync(self, query: str, candidates: list[dict[str, Any]]) -> list[float]:
        """Synchronous re-ranking: tokenize → infer → return logits."""
        assert self._tokenizer is not None
        assert self._model is not None

        import torch  # type: ignore[import-not-found]

        texts = [query] * len(candidates)
        passages = [c["content"] for c in candidates]

        inputs = self._tokenizer(
            texts,
            passages,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )

        with torch.no_grad():
            outputs = self._model(**inputs)
            # Cross-encoder returns logits for relevance
            raw_logits = outputs.logits.squeeze(-1)

        scores: list[float] = raw_logits.tolist()
        return scores

    @classmethod
    def is_loaded(cls) -> bool:
        """Return True if the model has been loaded."""
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset the model (useful for testing)."""
        cls._loaded = False
        cls._model = None
        cls._tokenizer = None
