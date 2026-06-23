"""LangGraph AgentState TypedDict.

Shared mutable state that flows through every node in the graph.
Each agent reads and writes one or more fields.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Mutable state carried through the LangGraph QA pipeline.

    Fields are optional (total=False) so the graph can populate them
    incrementally.  Every agent *must* handle missing keys gracefully.
    """

    # ── Input ──────────────────────────────────────────────────────────
    query: str
    session_id: str
    top_k: int

    # ── Router output ─────────────────────────────────────────────────
    query_type: str  # "semantic" | "keyword" | "hybrid" | "greeting" | "irrelevant"

    # ── Retriever output ──────────────────────────────────────────────
    retrieved_chunks: list[dict[str, Any]]

    # ── Reranker output ───────────────────────────────────────────────
    reranked_chunks: list[dict[str, Any]]

    # ── Answer generator output ───────────────────────────────────────
    answer_text: str
    citations: list[dict[str, Any]]
    confidence_score: float

    # ── Critic output ─────────────────────────────────────────────────
    critic_passed: bool
    critic_feedback: str
    critic_retries: int

    # ── Memory output ─────────────────────────────────────────────────
    history: list[dict[str, str]]  # last N {role, content} pairs

    # ── Synthesizer output ────────────────────────────────────────────
    final_response: str

    # ── Observability ─────────────────────────────────────────────────
    agent_states: dict[str, str]  # agent_name → status for /pipeline/status

    # ── Error handling ────────────────────────────────────────────────
    error: str

    # ── Dependency injection (runtime only, not serialised) ───────────
    _db_session: Any       # AsyncSession (injected at call site)
    _embedding_model: Any  # EmbeddingModel (injected at call site)
    _settings: Any         # Settings (injected at call site)
