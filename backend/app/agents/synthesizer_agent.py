"""SynthesizerAgent — produces the final polished response.

Formats the answer with citations and conversation history into a clean,
user-facing response.  Handles greetings and irrelevant queries gracefully.
"""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState


# ── Greeting responses ───────────────────────────────────────────────────────

_GREETING_RESPONSES: dict[str, str] = {
    "greeting": (
        "Hello! I'm the RAG-CRM assistant. I can answer questions about your "
        "documents using a combination of semantic search, keyword matching, "
        "and AI-generated responses. How can I help you today?"
    ),
    "irrelevant": (
        "I'm sorry, but your query doesn't appear to be something I can help with. "
        "I'm designed to answer questions based on your document knowledge base. "
        "Please try asking a question about your documents."
    ),
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _format_citations(citations: list[dict[str, Any]]) -> str:
    """Format a list of citation dicts into a markdown bibliography."""
    if not citations:
        return ""
    lines: list[str] = ["\n---\n**Sources:**"]
    for i, cit in enumerate(citations, start=1):
        chunk_id = cit.get("chunk_id", "unknown")
        doc_id = cit.get("document_id", "unknown")
        snippet = cit.get("content_snippet", "")
        lines.append(f"{i}. `{chunk_id}` (document `{doc_id}`)")
        if snippet:
            lines.append(f"   > {snippet[:200]}")
    return "\n".join(lines)


def _format_history_context(history: list[dict[str, str]]) -> str:
    """Format conversation history as a compact reference (if non-empty)."""
    if not history:
        return ""
    lines: list[str] = ["\n---\n**Recent conversation:**"]
    for entry in history[-6:]:  # last 3 exchanges (6 messages)
        role = entry.get("role", "unknown")
        content = entry.get("content", "")
        prefix = "**Q:**" if role == "user" else "**A:**"
        # Truncate long messages
        if len(content) > 150:
            content = content[:147] + "..."
        lines.append(f"{prefix} {content}")
    return "\n".join(lines)


# ── LangGraph node ───────────────────────────────────────────────────────────


async def synthesizer_agent(state: AgentState) -> dict:
    """LangGraph node: produce the final response string.

    Routes by ``query_type``:
      - ``greeting`` / ``irrelevant`` → canned response
      - ``semantic`` / ``keyword`` / ``hybrid`` → formatted answer with
        citations, confidence, and conversation history.

    Returns ``final_response`` and an updated ``agent_states`` entry.
    """
    query_type: str = state.get("query_type", "hybrid")
    answer_text: str = state.get("answer_text", "")
    citations: list[dict[str, Any]] = state.get("citations", [])
    confidence_score: float = state.get("confidence_score", 0.0)
    history: list[dict[str, str]] = state.get("history", [])
    critic_feedback: str = state.get("critic_feedback", "")

    # ── Error state ────────────────────────────────────────────────────
    error: str = state.get("error", "")
    if error:
        final = (
            f"I'm sorry, but I encountered an error processing your question: "
            f"{error}\n\nPlease try again or rephrase your question."
        )
        return {
            "final_response": final,
            "agent_states": {
                **(state.get("agent_states") or {}),
                "synthesizer": "completed",
            },
        }

    # ── Early-exit types ───────────────────────────────────────────────
    if query_type == "greeting":
        final = _GREETING_RESPONSES["greeting"]
    elif query_type == "irrelevant":
        final = _GREETING_RESPONSES["irrelevant"]
    else:
        # ── Build the substantive response ───────────────────────────────
        parts: list[str] = []

        # Main answer
        parts.append(answer_text)

        # Confidence (if meaningful)
        if confidence_score > 0:
            parts.append(f"\n*Confidence: {confidence_score:.0%}*")

        # Citations
        citations_block = _format_citations(citations)
        if citations_block:
            parts.append(citations_block)

        # Critic note (if the answer was accepted despite failing checks)
        if critic_feedback and not state.get("critic_passed", True):
            parts.append(
                f"\n> ⚠️ **Quality note:** {critic_feedback}"
            )

        # Conversation history context
        history_block = _format_history_context(history)
        if history_block:
            parts.append(history_block)

        final = "\n".join(parts)

    return {
        "final_response": final,
        "agent_states": {
            **(state.get("agent_states") or {}),
            "synthesizer": "completed",
        },
    }
