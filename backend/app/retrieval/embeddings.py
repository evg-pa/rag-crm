"""BGE-Small ONNX embedding model with lazy loading and session caching.

Loads the BAAI/bge-small-en-v1.5 model via optimum.onnxruntime on first use,
not at import time. Inference runs in a thread-pool executor so callers can
await it without blocking the event loop.

Session caching: the ONNX Runtime InferenceSession is created once per process
with tuned SessionOptions (graph optimization level, thread parallelism) and
reused across all subsequent requests. The model and tokenizer are also cached
at the class level, protected by an asyncio.Lock for thread safety.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.core.dependencies import get_settings

logger = logging.getLogger(__name__)

# Map config strings to onnxruntime GraphOptimizationLevel constants.
# Initialised eagerly at module-level to avoid thread-safety issues
# with lazy mutable dict updates.
try:
    import onnxruntime as ort
    _OPTIMIZATION_LEVEL_MAP: dict[str, Any] = {
        "disable": ort.GraphOptimizationLevel.ORT_DISABLE_ALL,
        "basic": ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
        "extended": ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
        "all": ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
    }
except ImportError:
    # onnxruntime not installed — will be caught at model load time.
    _OPTIMIZATION_LEVEL_MAP = {}  # type: ignore[assignment]


def _get_optimization_level(level_name: str) -> Any:
    """Resolve a named optimization level to the onnxruntime constant.

    Logs a warning and falls back to 'all' when the name is unrecognised.
    """
    normalized = level_name.lower()
    if normalized in _OPTIMIZATION_LEVEL_MAP:
        return _OPTIMIZATION_LEVEL_MAP[normalized]
    logger.warning(
        "Unrecognised ONNX_GRAPH_OPTIMIZATION_LEVEL '%s' — falling back to 'all'",
        level_name,
    )
    return _OPTIMIZATION_LEVEL_MAP.get("all")


class EmbeddingModel:
    """Lazy-loading BGE-Small ONNX embedding model.

    Thread-safe: only one load per process, protected by asyncio.Lock
    so concurrent first-calls don't double-load.

    The underlying ONNX Runtime ``InferenceSession`` is created with
    tuned ``SessionOptions`` (graph optimization level, thread counts)
    and cached for the process lifetime — every subsequent ``embed()``
    or ``embed_batch()`` call reuses the same session.
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

    # Upper bound for ONNX thread pool sizes to prevent accidental CPU oversubscription.
    _MAX_ONNX_THREADS: int = 128

    @classmethod
    def _ensure_loaded(cls) -> None:
        """Blocking load of the ONNX model and tokenizer.

        Called inside the async lock — must not be called directly from
        async context without the lock held.

        Configures ONNX Runtime SessionOptions for:
        - Graph optimization level (via ``ONNX_GRAPH_OPTIMIZATION_LEVEL``)
        - Intra-op thread parallelism (via ``ONNX_INTRA_OP_THREADS``)
        - Inter-op thread parallelism (via ``ONNX_INTER_OP_THREADS``)

        Thread counts are capped at _MAX_ONNX_THREADS to prevent
        accidental CPU oversubscription.
        """
        if cls._loaded:
            return

        # Reset partial state in case of previous failed load.
        cls._tokenizer = None
        cls._model = None

        import onnxruntime as ort
        from optimum.onnxruntime import (  # type: ignore[import-not-found,unused-ignore]
            ORTModelForFeatureExtraction,
        )
        from transformers import AutoTokenizer  # type: ignore[import-not-found,unused-ignore]

        settings = get_settings()

        # Build SessionOptions for the ONNX Runtime inference session.
        # These are passed to ORTModelForFeatureExtraction so that the
        # underlying InferenceSession uses them for all subsequent runs.
        session_options = ort.SessionOptions()
        session_options.graph_optimization_level = _get_optimization_level(
            settings.ONNX_GRAPH_OPTIMIZATION_LEVEL
        )
        if settings.ONNX_INTRA_OP_THREADS > 0:
            intra = min(settings.ONNX_INTRA_OP_THREADS, cls._MAX_ONNX_THREADS)
            session_options.intra_op_num_threads = intra
            if intra < settings.ONNX_INTRA_OP_THREADS:
                logger.warning(
                    "ONNX_INTRA_OP_THREADS=%d capped at %d",
                    settings.ONNX_INTRA_OP_THREADS,
                    cls._MAX_ONNX_THREADS,
                )
        if settings.ONNX_INTER_OP_THREADS > 0:
            inter = min(settings.ONNX_INTER_OP_THREADS, cls._MAX_ONNX_THREADS)
            session_options.inter_op_num_threads = inter
            if inter < settings.ONNX_INTER_OP_THREADS:
                logger.warning(
                    "ONNX_INTER_OP_THREADS=%d capped at %d",
                    settings.ONNX_INTER_OP_THREADS,
                    cls._MAX_ONNX_THREADS,
                )

        logger.info(
            "Loading embedding model %s (opt_level=%s, intra_threads=%s, inter_threads=%s)",
            settings.EMBEDDING_MODEL,
            settings.ONNX_GRAPH_OPTIMIZATION_LEVEL,
            session_options.intra_op_num_threads,
            session_options.inter_op_num_threads,
        )

        try:
            cls._tokenizer = AutoTokenizer.from_pretrained(settings.EMBEDDING_MODEL)
            cls._model = ORTModelForFeatureExtraction.from_pretrained(
                settings.EMBEDDING_MODEL,
                export=False,
                session_options=session_options,
            )
        except Exception:
            # Clean up partial state so a later retry starts fresh.
            cls._tokenizer = None
            cls._model = None
            logger.exception(
                "Failed to load embedding model %s", settings.EMBEDDING_MODEL
            )
            raise

        cls._loaded = True
        logger.info("Embedding model loaded and cached for process lifetime")

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
