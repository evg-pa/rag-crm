"""MemoryAgent — stores/retrieves conversation memory in PostgreSQL.

Replaces the previous in-memory store with persistent storage:

- **Working Memory:** session Q&A history (PostgreSQL, pruned to last 5 exchanges)
- **Episodic Memory:** cross-session conversation summaries (created after QA completes)
- **Semantic Memory:** extracted facts with pgvector embeddings
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.memory.service import (
    EpisodicMemoryService,
    WorkingMemoryService,
)

logger = get_logger(__name__)

# Maximum number of exchanges (user + assistant pairs) to retain per session
MAX_EXCHANGES: int = 5


async def memory_agent(state: AgentState) -> dict[str, Any]:
    """LangGraph node: persist the current Q&A turn to PostgreSQL.

    Expects ``query``, ``answer_text``, and ``session_id`` in *state*.
    Returns an updated ``history`` list (last 5 exchanges) and an updated
    ``agent_states`` entry.
    """
    query: str = state.get("query", "")
    answer_text: str = state.get("answer_text", "")
    session_id: str = state.get("session_id", "default")
    db: AsyncSession | None = state.get("_db_session")

    history: list[dict[str, str]] = []

    if db is not None:
        try:
            wm_service = WorkingMemoryService(db)

            # Store user query
            await wm_service.add_message(
                session_id=session_id,
                role="user",
                content=query,
            )

            # Store assistant response (if present)
            if answer_text:
                await wm_service.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=answer_text,
                )

            # Retrieve updated history
            history = await wm_service.get_history(
                session_id=session_id,
                limit=MAX_EXCHANGES * 2,
            )
        except Exception:
            logger.warning(
                "Working memory write failed for session %s",
                session_id,
                exc_info=True,
            )
    else:
        logger.warning(
            "No DB session available — working memory not persisted"
        )

    # Build history in the format expected by downstream agents
    formatted_history: list[dict[str, str]] = [
        {"role": h["role"], "content": h["content"]} for h in history
    ]

    return {
        "history": formatted_history,
        "agent_states": {
            **(state.get("agent_states") or {}),
            "memory": "completed",
        },
    }


async def create_episodic_summary(
    db: AsyncSession,
    session_id: str,
    history: list[dict[str, str]],
    llm_summary: str | None = None,
    topics: list[str] | None = None,
) -> None:
    """Create or update an episodic memory entry for a session.

    Called after a QA session completes to preserve a high-level
    summary of the conversation.
    """
    if not history:
        return

    # Count messages
    message_count = len(history)

    # Use provided summary or generate a simple one
    summary = llm_summary or _auto_summarize(history)
    conversation_topics = topics or _extract_topics(history)

    service = EpisodicMemoryService(db)
    await service.create_or_update(
        session_id=session_id,
        summary=summary,
        topics=conversation_topics,
        message_count=message_count,
    )


def _auto_summarize(history: list[dict[str, str]]) -> str:
    """Generate a basic summary from conversation history."""
    if not history:
        return ""

    # Extract the first user query as the topic
    user_messages = [
        h["content"] for h in history if h.get("role") == "user"
    ]
    if user_messages:
        first_query = user_messages[0]
        if len(first_query) > 120:
            first_query = first_query[:117] + "..."
        return f"Conversation about: {first_query}"

    return "Conversation with no recorded queries"


def _extract_topics(history: list[dict[str, str]]) -> list[str]:
    """Extract basic topics from conversation history."""
    # Simple keyword extraction from user messages
    user_messages = [
        h["content"] for h in history if h.get("role") == "user"
    ]
    topics: set[str] = set()
    for msg in user_messages:
        words = msg.lower().split()
        # Simple heuristic: capitalize short meaningful words as topics
        for w in words:
            w_clean = w.strip(".,!?()[]{}:;\"'")
            if 4 <= len(w_clean) <= 20 and not w_clean.isdigit():
                topics.add(w_clean.capitalize())

    # Limit to 10 topics
    return sorted(topics)[:10]


# ── Standalone helpers for API use ──────────────────────────────────────────


async def get_working_history(
    db: AsyncSession, session_id: str, limit: int = MAX_EXCHANGES * 2
) -> list[dict[str, str]]:
    """Retrieve the working memory history for a session."""
    service = WorkingMemoryService(db)
    return await service.get_history(
        session_id=session_id, limit=limit
    )


async def clear_working_memory(
    db: AsyncSession, session_id: str
) -> int:
    """Clear working memory for a session."""
    service = WorkingMemoryService(db)
    return await service.clear_session(session_id=session_id)
