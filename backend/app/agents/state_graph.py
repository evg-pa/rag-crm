"""LangGraph StateGraph — wires the 7-agent pipeline together.

Builds and compiles a LangGraph ``StateGraph`` with conditional routing:
- Router → (irrelevant → END | greeting → Synthesizer → END | rest → Retriever)
- Retriever → Reranker → Answer → Critic
- Critic → (pass → Memory → Synthesizer → END | fail+retries<2 → Answer | fail+retries≥2 → Memory)
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.answer_agent import answer_agent
from app.agents.critic_agent import MAX_CRITIC_RETRIES, critic_agent
from app.agents.memory_agent import memory_agent
from app.agents.reranker_agent import reranker_agent
from app.agents.retriever_agent import retriever_agent
from app.agents.router_agent import router_agent
from app.agents.state import AgentState
from app.agents.synthesizer_agent import synthesizer_agent


# ── Routing helpers ──────────────────────────────────────────────────────────


def _route_after_router(state: AgentState) -> str:
    """Decide the next node after RouterAgent classifies the query.

    Returns
    -------
    str
        ``"retriever"`` for search-based queries, ``"synthesizer"`` for
        greeting/irrelevant (canned response path) or errors.
    """
    error: str = state.get("error", "")
    if error:
        return "synthesizer"

    query_type: str = state.get("query_type", "hybrid")

    if query_type in ("greeting", "irrelevant"):
        return "synthesizer"
    return "retriever"


def _route_after_critic(state: AgentState) -> str:
    """Decide the next node after CriticAgent validates the answer.

    Returns
    -------
    str
        ``"memory"`` if the answer passes critcism, max retries are
        exhausted, or an error occurred; ``"answer"`` to retry generation.
    """
    error: str = state.get("error", "")
    if error:
        return "memory"

    critic_passed: bool = state.get("critic_passed", False)
    retries: int = state.get("critic_retries", 0)

    if critic_passed:
        return "memory"
    if retries < MAX_CRITIC_RETRIES:
        return "answer"
    return "memory"


# ── Graph builder ────────────────────────────────────────────────────────────


def build_qa_graph() -> StateGraph:
    """Build and compile the 7-agent LangGraph QA pipeline.

    Returns a compiled graph that can be invoked with ``ainvoke(state)``.
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ────────────────────────────────────────────────────────
    graph.add_node("router", router_agent)
    graph.add_node("retriever", retriever_agent)
    graph.add_node("reranker", reranker_agent)
    graph.add_node("answer", answer_agent)
    graph.add_node("critic", critic_agent)
    graph.add_node("memory", memory_agent)
    graph.add_node("synthesizer", synthesizer_agent)

    # ── Set entry point ──────────────────────────────────────────────────
    graph.set_entry_point("router")

    # ── Conditional edge from router ─────────────────────────────────────
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {
            "retriever": "retriever",
            "synthesizer": "synthesizer",
        },
    )

    # ── Linear retrieval chain ───────────────────────────────────────────
    graph.add_edge("retriever", "reranker")
    graph.add_edge("reranker", "answer")

    # ── Critic loop ──────────────────────────────────────────────────────
    graph.add_edge("answer", "critic")
    graph.add_conditional_edges(
        "critic",
        _route_after_critic,
        {
            "answer": "answer",
            "memory": "memory",
        },
    )

    # ── Final chain ──────────────────────────────────────────────────────
    graph.add_edge("memory", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile()  # default recursion_limit=25 is safe for our 14-node max path
