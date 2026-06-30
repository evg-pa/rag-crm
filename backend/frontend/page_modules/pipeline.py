"""Page 6: Pipeline — LangGraph agent status and monitoring."""

from __future__ import annotations

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from components.pipeline_diagram import pipeline_diagram, pipeline_table
from utils import api
from utils.i18n import _


def render() -> None:
    """Render the Pipeline Dashboard page."""
    st.title(_("pipeline.title"))
    st.caption(_("pipeline.caption"))

    # ── Auto-refresh controls ───────────────────────────────────────────
    col_auto, col_refresh = st.columns(2)
    with col_auto:
        auto_refresh = st.checkbox(
            _("pipeline.auto_refresh"),
            value=False,
            key="pipeline_auto_refresh",
        )
        if auto_refresh:
            st_autorefresh(interval=10000, key="pipeline_autorefresh")
    with col_refresh:
        if st.button(_("pipeline.refresh"), key="pipeline_refresh_btn", use_container_width=True):
            pass  # Will refresh below

    # ── Fetch pipeline status ───────────────────────────────────────────
    try:
        status = api.pipeline_status()
        agents = status.get("agents", {})
        pipeline_state = status.get("pipeline", "unknown")
    except Exception as exc:
        st.error(_("pipeline.connect_err", err=exc))
        return

    # ── Flow Diagram ────────────────────────────────────────────────────
    st.subheader(_("pipeline.agent_flow"))
    pipeline_diagram(agents)

    st.divider()

    # ── Agent Stats Table ───────────────────────────────────────────────
    st.subheader(_("pipeline.agent_details"))

    agent_stats = [
        {
            "name": name,
            "status": agent_status,
            "avg_latency_ms": "—",
            "total_calls": "—",
        }
        for name, agent_status in agents.items()
    ]
    pipeline_table(agent_stats)

    # ── System info ─────────────────────────────────────────────────────
    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        health = None
        try:
            health = api.health_check()
        except Exception:
            pass

        db_status = health.get("database", "?") if health else "offline"
        app_version = health.get("version", "?") if health else "?"
        st.metric(
            _("pipeline.pipeline_state"),
            pipeline_state.capitalize(),
            delta=None,
        )
    with col2:
        st.metric(_("pipeline.database"), db_status.capitalize())
    with col3:
        st.metric(_("pipeline.backend_ver"), app_version)

    # ── Notes ───────────────────────────────────────────────────────────
    with st.expander(_("pipeline.about"), expanded=False):
        st.markdown("""
        **LangGraph 7-Agent Pipeline:**
        
        1. **RouterAgent** — Classifies the query type and selects retrieval strategy
        2. **RetrieverAgent** — Runs semantic (pgvector) + BM25 keyword hybrid search
        3. **RerankerAgent** — Re-ranks top results with BGE-Reranker cross-encoder
        4. **AnswerAgent** — Generates the answer via DeepSeek or Ollama LLM
        5. **CriticAgent** — Validates answer quality (up to 2 retries)
        6. **MemoryAgent** — Stores the exchange in session history
        7. **SynthesizerAgent** — Produces the final polished response
        
        Each agent has a status: 🟢 **idle** (ready), 🟡 **active** (processing), 
        or 🔴 **error** (failed).
        """)
