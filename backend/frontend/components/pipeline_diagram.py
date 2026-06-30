"""Pipeline diagram and table components."""

from __future__ import annotations

import streamlit as st

from utils.i18n import _

AGENT_DISPLAY_ORDER = [
    "router",
    "retriever",
    "reranker",
    "answer",
    "critic",
    "memory",
    "synthesizer",
]

AGENT_LABELS: dict[str, str] = {
    "router": "Router",
    "retriever": "Retriever",
    "reranker": "Reranker",
    "answer": "Answer",
    "critic": "Critic",
    "memory": "Memory",
    "synthesizer": "Synthesizer",
}


def _status_class(status: str) -> str:
    """Map a status string to a CSS class."""
    if status in ("idle", "ready"):
        return "idle"
    if status in ("running", "active", "processing"):
        return "active"
    return "error"


def _status_dot(status: str) -> str:
    """Return a colored dot for a status string."""
    if status in ("idle", "ready"):
        return "🟢"
    if status in ("running", "active", "processing"):
        return "🟡"
    return "🔴"


def pipeline_diagram(agents: dict[str, str]) -> None:
    """Render the agent pipeline flow diagram.

    Args:
        agents: Mapping of agent_name → status (e.g. {"router": "idle", ...}).
    """
    parts: list[str] = []
    for i, name in enumerate(AGENT_DISPLAY_ORDER):
        status = agents.get(name, "unknown")
        cls = _status_class(status)
        label = AGENT_LABELS.get(name, name)
        dot = _status_dot(status)
        parts.append(f'<span class="rag-pipeline-agent {cls}">{dot} {label}</span>')
        if i < len(AGENT_DISPLAY_ORDER) - 1:
            parts.append('<span class="rag-pipeline-arrow">→</span>')

    st.markdown(
        f'<div class="rag-pipeline-flow">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def pipeline_table(agent_stats: list[dict]) -> None:
    """Render the agent statistics table.

    Args:
        agent_stats: List of dicts with keys: name, status, avg_latency_ms, total_calls.
    """
    rows: list[dict] = []
    for stat in agent_stats:
        name = stat.get("name", "unknown")
        status = stat.get("status", "unknown")
        latency = stat.get("avg_latency_ms", "—")
        calls = stat.get("total_calls", "—")

        dot = _status_dot(status)
        label = AGENT_LABELS.get(name, name)

        rows.append({
            _('pipe.agent'): label,
            _('pipe.status'): f"{dot} {status}",
            _('pipe.avg_latency'): str(latency),
            _('pipe.total_calls'): str(calls),
        })

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            _('pipe.agent'): st.column_config.TextColumn(_('pipe.agent'), width="medium"),
            _('pipe.status'): st.column_config.TextColumn(_('pipe.status'), width="small"),
            _('pipe.avg_latency'): st.column_config.TextColumn(_('pipe.avg_latency'), width="small"),
            _('pipe.total_calls'): st.column_config.TextColumn(_('pipe.total_calls'), width="small"),
        },
    )
