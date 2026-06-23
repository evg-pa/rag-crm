"""CriticAgent — validates the generated answer against the retrieved sources.

Implements a max-2-retries loop via LangGraph conditional edges.
The node itself is stateless: it reads state, decides pass/fail, and
increments the retry counter.  The routing logic in state_graph.py
decides whether to loop back to AnswerAgent or proceed to MemoryAgent.
"""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState

# ── Configuration ───────────────────────────────────────────────────────────

MAX_CRITIC_RETRIES: int = 2

# Minimum number of citations expected for a well-sourced answer
MIN_CITATIONS: int = 1

# Minimum fraction of claims that must be supported by chunks
MIN_CLAIM_SUPPORT_RATIO: float = 0.3


# ── Helpers ─────────────────────────────────────────────────────────────────


def _has_citations(citations: list[dict[str, Any]]) -> bool:
    """Check 1: answer cites sources."""
    return len(citations) >= MIN_CITATIONS


def _claims_supported(answer_text: str, chunks: list[dict[str, Any]]) -> tuple[bool, float]:
    """Check 2: what fraction of answer claims are backed by retrieved chunks?

    A simple word-overlap heuristic: for each sentence in the answer, check
    whether a meaningful fraction of its content words appear in any chunk.
    Returns (passed, support_ratio).
    """
    if not answer_text or not chunks:
        return False, 0.0

    # Normalise text for comparison
    import re

    def _normalise(t: str) -> str:
        return t.lower().strip()

    # Collect all content words from chunks (stopword-filtered)
    chunk_words: set[str] = set()
    for c in chunks:
        content = _normalise(c.get("content", ""))
        for word in re.findall(r"\b[a-z]{3,}\b", content):
            chunk_words.add(word)

    if not chunk_words:
        return True, 1.0  # no chunks to check against → assume fine

    # Split answer into sentences (crude split)
    sentences = re.split(r"[.!?\n]+", _normalise(answer_text))
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        # Answer too short to meaningfully check → pass
        return True, 1.0

    supported_count = 0
    for sentence in sentences:
        words = set(re.findall(r"\b[a-z]{3,}\b", sentence))
        if not words:
            supported_count += 1  # no content words → assume fine
            continue
        # Sentence is "supported" if >= 40% of its content words appear in chunks
        overlap = words & chunk_words
        if len(overlap) / len(words) >= 0.4:
            supported_count += 1

    support_ratio = supported_count / len(sentences)
    return support_ratio >= MIN_CLAIM_SUPPORT_RATIO, support_ratio


# ── LangGraph node ───────────────────────────────────────────────────────────


async def critic_agent(state: AgentState) -> dict:
    """LangGraph node: validate the answer against retrieved sources.

    Runs two checks:
      1. Answer cites sources (has at least one citation).
      2. A meaningful fraction of answer claims appear in retrieved chunks.

    On failure, increments ``critic_retries`` and provides ``critic_feedback``
    so the AnswerAgent can retry with guidance.

    After ``MAX_CRITIC_RETRIES`` failures, forces ``critic_passed = True``
    to prevent an infinite loop.
    """
    answer_text: str = state.get("answer_text", "")
    citations: list[dict[str, Any]] = state.get("citations", [])
    chunks: list[dict[str, Any]] = state.get("reranked_chunks", [])
    retries: int = state.get("critic_retries", 0)

    feedback_parts: list[str] = []

    # ── Check 1: citations ──────────────────────────────────────────────
    has_citations = _has_citations(citations)
    if not has_citations:
        feedback_parts.append(
            "MISSING CITATIONS: Your answer does not cite any sources. "
            "Please include at least one citation linking back to the chunk IDs "
            "provided in the context."
        )

    # ── Check 2: claim support ──────────────────────────────────────────
    claims_ok, support_ratio = _claims_supported(answer_text, chunks)
    if not claims_ok:
        feedback_parts.append(
            f"UNSUPPORTED CLAIMS: Only {support_ratio:.0%} of your claims overlap "
            "with the retrieved chunks. Make sure every factual statement in your "
            "answer is grounded in the provided context."
        )

    critic_passed = has_citations and claims_ok

    # Force pass after max retries
    if retries >= MAX_CRITIC_RETRIES:
        critic_passed = True
        feedback_parts.append("(Max retries reached — proceeding with current answer.)")

    next_retries = retries + (0 if critic_passed else 1)

    return {
        "critic_passed": critic_passed,
        "critic_feedback": "\n".join(feedback_parts) if feedback_parts else "",
        "critic_retries": next_retries,
        "agent_states": {
            **(state.get("agent_states") or {}),
            "critic": "completed",
        },
    }
