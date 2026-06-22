"""BM25 keyword search with lazy in-memory index.

Uses the pure-Python ``rank_bm25`` library.  The index is built from all
chunk content in the database on first search (lazy init) and can be
explicitly rebuilt when new documents are ingested.
"""

from __future__ import annotations

import asyncio
from typing import Any

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


class BM25Index:
    """In-memory BM25 keyword index over all chunk content.

    Thread-safe lazy init: the index is built on the first ``search()``
    call, not at import time.  Call ``rebuild()`` after ingesting new
    documents to keep the index fresh.
    """

    _index: BM25Okapi | None = None
    _chunk_metadata: list[dict[str, Any]] | None = None
    _lock: asyncio.Lock | None = None
    _loaded: bool = False

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def _ensure_loaded(cls, db: AsyncSession | None = None) -> None:
        """Build the BM25 index if not already loaded.

        Requires a database session.  If called without one while the
        index hasn't been built, raises RuntimeError.
        """
        if cls._loaded:
            return

        lock = cls._get_lock()
        async with lock:
            if cls._loaded:
                return
            if db is None:
                raise RuntimeError(
                    "BM25Index not loaded and no database session provided."
                )
            await cls._build_index(db)

    @classmethod
    async def _build_index(cls, db: AsyncSession) -> None:
        """Build the BM25 index from all chunks in the database."""
        result = await db.execute(select(Chunk).order_by(Chunk.chunk_index))
        chunks = result.scalars().all()

        if not chunks:
            # Empty corpus: store empty index so we don't rebuild on every call
            cls._chunk_metadata = []
            cls._index = BM25Okapi([["__empty__"]])
            cls._loaded = True
            return

        tokenized_corpus: list[list[str]] = []
        metadata: list[dict[str, Any]] = []

        for chunk in chunks:
            tokenized_corpus.append(_tokenize(chunk.content))
            metadata.append(
                {
                    "id": str(chunk.id),
                    "content": chunk.content,
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                }
            )

        cls._index = BM25Okapi(tokenized_corpus)
        cls._chunk_metadata = metadata
        cls._loaded = True

    @classmethod
    async def search(
        cls,
        query: str,
        top_k: int = 10,
        db: AsyncSession | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k chunks ranked by BM25 score.

        Results are ordered by descending BM25 score.  Each dict contains
        ``id``, ``content``, ``document_id``, ``chunk_index``, and
        ``bm25_score``.
        """
        await cls._ensure_loaded(db)

        assert cls._index is not None
        assert cls._chunk_metadata is not None

        if not cls._chunk_metadata:
            return []

        tokenized_query = _tokenize(query)
        scores = cls._index.get_scores(tokenized_query)

        # Pair scores with metadata, sort descending, take top_k
        scored: list[tuple[float, dict[str, Any]]] = sorted(
            zip(scores, cls._chunk_metadata, strict=True),
            key=lambda pair: pair[0],
            reverse=True,
        )[:top_k]

        return [
            {
                **meta,
                "bm25_score": round(float(score), 6),
            }
            for score, meta in scored
            if score > 0
        ] or []

    @classmethod
    async def rebuild(cls, db: AsyncSession) -> None:
        """Rebuild the BM25 index from the current database contents.

        Call this after ingesting new documents.
        """
        cls._loaded = False
        cls._index = None
        cls._chunk_metadata = None
        await cls._build_index(db)
        cls._loaded = True

    @classmethod
    def is_loaded(cls) -> bool:
        """Return True if the index has been built."""
        return cls._loaded

    @classmethod
    def reset(cls) -> None:
        """Reset the index (useful for testing)."""
        cls._loaded = False
        cls._index = None
        cls._chunk_metadata = None


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenization with lowercasing."""
    return text.lower().split()
