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


def _has_citations(citations: list) -> bool:
    """Return True if citations list is non-empty."""
    return len(citations) > 0


def _validate_citations(
    citations: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Check 1: answer cites sources AND those sources exist in retrieved chunks.

    Returns (passed, feedback_message).
    """
    if not citations or len(citations) < MIN_CITATIONS:
        return False, (
            "MISSING CITATIONS: Your answer does not cite any sources. "
            "Please include at least one citation linking back to the chunk IDs "
            "provided in the context."
        )

    # FIX 3: validate that citation chunk_ids reference actual chunk IDs
    valid_chunk_ids: set[str] = {c.get("id", "") for c in chunks if c.get("id")}
    invalid_citations: list[str] = []
    for cit in citations:
        cid = cit.get("chunk_id", "")
        if cid and cid not in valid_chunk_ids:
            invalid_citations.append(cid)

    if invalid_citations:
        return False, (
            f"INVALID CITATIONS: The following chunk IDs do not exist in the retrieved "
            f"context: {', '.join(invalid_citations)}. "
            f"Please cite only chunk IDs from the provided context."
        )

    return True, ""


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

    # FIX 1: empty chunk_words means chunks have no usable content — cannot validate
    if not chunk_words:
        return False, 0.0

    # Split answer into sentences (crude split)
    all_sentences = [s.strip() for s in re.split(r"[.!?\n]+", _normalise(answer_text)) if s.strip()]

    if not all_sentences:
        return False, 0.0

    # FIX 2: include short sentences in the total count for an honest support ratio.
    # Sentences below the minimum length are counted in the denominator but
    # treated as unsupported (they cannot be meaningfully validated).
    MIN_SENTENCE_LENGTH = 20

    supported_count = 0
    short_count = 0
    for sentence in all_sentences:
        if len(sentence) <= MIN_SENTENCE_LENGTH:
            short_count += 1
            continue
        words = set(re.findall(r"\b[a-z]{3,}\b", sentence))
        if not words:
            continue  # no content words → cannot validate → count as unsupported
        # Sentence is "supported" if >= 40% of its content words appear in chunks
        overlap = words & chunk_words
        if len(overlap) / len(words) >= 0.4:
            supported_count += 1

    total_sentences = len(all_sentences)
    support_ratio = supported_count / total_sentences
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

    # ── Check 1: citation existence + validity ─────────────────────────
    citations_ok, citation_feedback = _validate_citations(citations, chunks)
    if not citations_ok:
        feedback_parts.append(citation_feedback)

    # ── Check 2: claim support ──────────────────────────────────────────
    claims_ok, support_ratio = _claims_supported(answer_text, chunks)
    if not claims_ok:
        feedback_parts.append(
            f"UNSUPPORTED CLAIMS: Only {support_ratio:.0%} of your claims overlap "
            "with the retrieved chunks. Make sure every factual statement in your "
            "answer is grounded in the provided context."
        )

    critic_passed = citations_ok and claims_ok

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
