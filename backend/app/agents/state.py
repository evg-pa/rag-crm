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
    query_type: str  # "semantic" | "keyword" | "hybrid" | "greeting" | "irrelevant" | "crm"

    # ── CRM Context output ────────────────────────────────────────────
    crm_query_type: str  # "contact" | "deal" | "activity" | "cross_reference" | "none"
    crm_entities: list[dict[str, Any]]  # extracted CRM entity names from query
    crm_context: str  # formatted CRM data injected as context
    crm_cross_refs: list[dict[str, Any]]  # cross-referenced document-chunk matches

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
    memory_type: str  # "working" | "episodic" | "semantic" | "none"
    extracted_facts: list[dict[str, Any]]  # facts for semantic memory

    # ── Knowledge Graph output ───────────────────────────────────────
    graph_entities: list[dict[str, Any]]  # expanded entities from graph
    graph_augmented_chunks: list[dict[str, Any]]  # chunks with graph scores

    # ── Synthesizer output ────────────────────────────────────────────
    final_response: str

    # ── Observability ─────────────────────────────────────────────────
    agent_states: dict[str, str]  # agent_name → status for /pipeline/status

    # ── Error handling ────────────────────────────────────────────────
    error: str

    # ── Dependency injection (runtime only, not serialised) ───────────
    _db_session: Any  # AsyncSession (injected at call site)
    _embedding_model: Any  # EmbeddingModel (injected at call site)
    _settings: Any  # Settings (injected at call site)
