"""MemoryAgent — stores/retrieves the last 5 conversation exchanges per session.

Thread-safe in-memory store keyed by ``session_id``.  Each exchange is a
{role: "user" | "assistant", content: str} pair.
"""

from __future__ import annotations

import threading
from collections import defaultdict, OrderedDict
from typing import Any

from app.agents.state import AgentState

# Maximum number of exchanges (user + assistant pairs) to retain per session
MAX_EXCHANGES: int = 5
# Total entries = 2 * MAX_EXCHANGES (one user, one assistant per exchange)
MAX_HISTORY_ENTRIES: int = MAX_EXCHANGES * 2

# Thread-safe in-memory store: session_id → list of {role, content}
_memory_store: dict[str, list[dict[str, str]]] = {}
_memory_lock: threading.Lock = threading.Lock()


def _trim_history(history: list[dict[str, str]], max_entries: int) -> list[dict[str, str]]:
    """Keep only the last *max_entries* from *history*."""
    if len(history) <= max_entries:
        return history
    return history[-max_entries:]


async def memory_agent(state: AgentState) -> dict:
    """LangGraph node: append the current Q&A turn to session history.

    Expects ``query``, ``answer_text``, and ``session_id`` in *state*.
    Returns an updated ``history`` list (last 5 exchanges) and an updated
    ``agent_states`` entry.
    """
    query: str = state.get("query", "")
    answer_text: str = state.get("answer_text", "")
    session_id: str = state.get("session_id", "default")

    with _memory_lock:
        history = _memory_store.get(session_id, [])

        # Append current turn
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": answer_text})

        # Trim to last 5 exchanges (10 entries)
        history = _trim_history(history, MAX_HISTORY_ENTRIES)
        _memory_store[session_id] = history

    return {
        "history": list(history),  # shallow copy for state
        "agent_states": {
            **(state.get("agent_states") or {}),
            "memory": "completed",
        },
    }


def get_history(session_id: str) -> list[dict[str, str]]:
    """Return the current history for a session (read-only)."""
    with _memory_lock:
        return list(_memory_store.get(session_id, []))


def clear_history(session_id: str) -> None:
    """Clear the history for a session."""
    with _memory_lock:
        _memory_store.pop(session_id, None)


def clear_all() -> None:
    """Clear all session histories (useful for testing)."""
    with _memory_lock:
        _memory_store.clear()
