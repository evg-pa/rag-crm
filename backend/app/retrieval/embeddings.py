"""BGE-Small ONNX embedding model with lazy loading.

Loads the BAAI/bge-small-en-v1.5 model via optimum.onnxruntime on first use,
not at import time. Inference runs in a thread-pool executor so callers can
await it without blocking the event loop.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.core.dependencies import get_settings


class EmbeddingModel:
    """Lazy-loading BGE-Small ONNX embedding model.

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
        """Blocking load of the ONNX model and tokenizer.

        Called inside the async lock — must not be called directly from
        async context without the lock held.
        """
        if cls._loaded:
            return

        from optimum.onnxruntime import ORTModelForFeatureExtraction  # type: ignore[import-not-found]
        from transformers import AutoTokenizer  # type: ignore[import-not-found]

        settings = get_settings()

        cls._tokenizer = AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL)
        cls._model = ORTModelForFeatureExtraction.from_pretrained(
            settings.EMBEDDING_MODEL,
            export=False,
        )
        cls._loaded = True

    async def _load(self) -> None:
        """Async-safe lazy loader: acquires a lock, runs blocking load."""
        lock = self._get_lock()
        async with lock:
            # Double-check after acquiring lock
            if not self._loaded:
                await asyncio.to_thread(self._ensure_loaded)

    async def embed(self, text: str) -> list[float]:
        """Return the L2-normalized embedding for a single text."""
        if not self._loaded:
            await self._load()

        # __call__ on the loaded model returns a tensor-like; must happen
        # in a thread because ORT inference is synchronous.
        return await asyncio.to_thread(self._embed_sync, text)

    def _embed_sync(self, text: str) -> list[float]:
        """Synchronous embedding: tokenize → infer → mean-pool → normalize."""
        assert self._tokenizer is not None
        assert self._model is not None

        encoded = self._tokenizer(
            text,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        outputs = self._model(**encoded)
        # Mean pooling — average the last_hidden_state over the token dim
        embeddings: NDArray[np.float32] = self._mean_pool(
            outputs.last_hidden_state, encoded["attention_mask"]
        )
        # L2 normalize
        emb_np = np.asarray(embeddings, dtype=np.float32)
        norm = np.linalg.norm(emb_np)
        if norm > 0:
            emb_np = emb_np / norm
        result: list[float] = emb_np.squeeze(axis=0).tolist()
        return result

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalized embeddings for a batch of texts.

        Batching is more efficient than calling `embed()` in a loop because
        the ONNX runtime can vectorize over the batch dimension.
        """
        if not texts:
            return []
        if not self._loaded:
            await self._load()
        return await asyncio.to_thread(self._embed_batch_sync, texts)

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous batch embedding."""
        assert self._tokenizer is not None
        assert self._model is not None

        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        outputs = self._model(**encoded)
        embeddings: NDArray[np.float32] = self._mean_pool(
            outputs.last_hidden_state, encoded["attention_mask"]
        )
        # L2 normalize each row
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # avoid division by zero
        embeddings = embeddings / norms

        result: list[list[float]] = embeddings.tolist()
        return result

    @staticmethod
    def _mean_pool(token_embeddings: Any, attention_mask: Any) -> NDArray[np.float32]:
        """Mean-pool token embeddings weighted by the attention mask.

        Returns a numpy array of shape (batch_size, hidden_dim).
        """
        import torch  # type: ignore[import-not-found]

        # Expand attention mask to match embedding dims
        mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        summed = torch.sum(token_embeddings * mask, dim=1)
        count = torch.clamp(mask.sum(dim=1), min=1e-9)
        pooled = summed / count
        result: NDArray[np.float32] = pooled.cpu().numpy().astype(np.float32)
        return result


@lru_cache
def get_embedding_model() -> EmbeddingModel:
    """Return a process-wide singleton EmbeddingModel."""
    return EmbeddingModel()
