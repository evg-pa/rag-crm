"""AnswerAgent — builds a context prompt and calls the LLM (DeepSeek/Ollama).

Reuses the prompt-building and LLM-calling logic from
app.retrieval.qa.AnswerAgent, adapted as a LangGraph node.
"""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState
from app.core.config import Settings
from app.retrieval.qa import AnswerAgent as LegacyAnswerAgent
from app.retrieval.qa import AnswerResult


async def answer_agent(state: AgentState) -> dict:
    """LangGraph node: generate an answer from reranked chunks via the LLM.

    Expects ``query``, ``reranked_chunks``, and optionally ``_settings``
    and ``critic_feedback`` (to inform the LLM on retries) in *state*.

    Returns ``answer_text``, ``citations``, ``confidence_score``, and an
    updated ``agent_states`` entry.
    """
    query: str = state.get("query", "")
    chunks: list[dict[str, Any]] = state.get("reranked_chunks", [])
    settings: Settings | None = state.get("_settings")  # type: ignore[typeddict-item]
    feedback: str = state.get("critic_feedback", "")
    retries: int = state.get("critic_retries", 0)

    top_k = min(len(chunks), 15)

    if not chunks:
        return {
            "answer_text": "I don't have enough information in the knowledge base to answer your question. Try uploading relevant documents first, or rephrase your query.",
            "citations": [],
            "confidence_score": 0.0,
            "agent_states": {
                **(state.get("agent_states") or {}),
                "answer": "completed",
            },
        }

    agent = LegacyAnswerAgent(settings=settings)
    try:
        # If critic provided feedback, prepend it to the query for retries
        effective_query = query
        if feedback and retries > 0:
            effective_query = (
                f"[CRITIC FEEDBACK — please address these issues in your response] "
                f"{feedback}\n\n"
                f"[ORIGINAL QUESTION] {query}"
            )

        result: AnswerResult = await agent.answer(
            query=effective_query,
            chunks=chunks,
            top_k=min(top_k, 100),
        )

        # Convert Citation objects to dicts for state serialisation
        citations: list[dict[str, Any]] = [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "content_snippet": c.content_snippet,
            }
            for c in result.citations
        ]

        return {
            "answer_text": result.answer_text,
            "citations": citations,
            "confidence_score": result.confidence_score,
            "agent_states": {
                **(state.get("agent_states") or {}),
                "answer": "completed",
            },
        }
    finally:
        await agent.close()
