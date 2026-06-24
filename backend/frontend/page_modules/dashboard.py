"""Page 1: Dashboard — system overview with KPI cards and pipeline summary."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from components.kpi_card import kpi_row
from components.crm_sync_status import crm_sync_status
from components.pipeline_diagram import pipeline_diagram
from utils import api, state


def _refresh_health() -> dict | None:
    """Refresh health status, caching for 30 seconds."""
    now = time.time()
    cached = st.session_state.get("health_cache")
    cached_time = st.session_state.get("health_cache_time", 0)

    if cached and (now - cached_time) < 30:
        return cached

    try:
        health = api.health_check()
        st.session_state.health_cache = health
        st.session_state.health_cache_time = now
        st.session_state.health_status = health
        return health
    except Exception:
        return None


def _refresh_pipeline() -> dict | None:
    """Refresh pipeline status, caching for 30 seconds."""
    now = time.time()
    cached_time = st.session_state.get("pipeline_status_time", 0)
    cached = st.session_state.get("pipeline_status")

    if cached and (now - cached_time) < 30:
        return cached

    try:
        status = api.pipeline_status()
        st.session_state.pipeline_status = status
        st.session_state.pipeline_status_time = now
        return status
    except Exception:
        return None


def _refresh_documents() -> list:
    """Refresh document list, caching for 60 seconds."""
    now = time.time()
    cached_time = st.session_state.get("documents_cache_time", 0)
    cached = st.session_state.get("documents_cache")

    if cached is not None and (now - cached_time) < 60:
        return cached

    try:
        docs = api.list_documents()
        st.session_state.documents_cache = docs
        st.session_state.documents_cache_time = now
        return docs
    except Exception:
        return cached if cached is not None else []


def render() -> None:
    """Render the Dashboard page."""
    st.title("📊 Dashboard")

    # ── Auto-refresh ────────────────────────────────────────────────────
    auto = st.session_state.get("dashboard_auto_refresh", False)
    if auto:
        st_autorefresh(interval=30000, key="dashboard_autorefresh")

    # Refresh data
    with st.spinner("Loading dashboard..."):
        health = _refresh_health()
        pipeline = _refresh_pipeline()
        docs = _refresh_documents()

    if not health and not docs:
        st.error("❌ Cannot connect to backend. Is the server running at `localhost:8000`?")
        return

    # ── KPI Row ──────────────────────────────────────────────────────────
    st.subheader("Overview")

    doc_count = len(docs)
    chunk_count = sum(
        len(d.get("chunks", [])) for d in docs
    )

    app_version = health.get("version", "?") if health else "?"
    db_status = health.get("database", "?") if health else "?"
    backend_status = "🟢 Online" if health else "🔴 Offline"

    kpi_row([
        ("Documents", doc_count, "📄"),
        ("Chunks", chunk_count, "🧩"),
        ("Backend", backend_status, ""),
        ("Version", app_version, "📦"),
    ])

    # ── CRM Sync Status ──────────────────────────────────────────────────
    st.subheader("CRM Sync")
    crm_sync_status()

    # ── Two-column layout ────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Recent Documents")
        if docs:
            recent = sorted(
                docs,
                key=lambda d: d.get("created_at", ""),
                reverse=True,
            )[:5]
            for doc in recent:
                filename = doc.get("filename", "unknown")
                created = doc.get("created_at", "")
                content_type = doc.get("content_type", "")
                size = doc.get("file_size", 0)

                # Format
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    diff = int((now - dt).total_seconds())
                    if diff < 60:
                        ago = "just now"
                    elif diff < 3600:
                        ago = f"{diff // 60}m ago"
                    elif diff < 86400:
                        ago = f"{diff // 3600}h ago"
                    else:
                        ago = f"{diff // 86400}d ago"
                except (ValueError, TypeError):
                    ago = "—"

                size_str = (
                    f"{size / 1024:.1f} KB" if size < 1024 * 1024
                    else f"{size / (1024*1024):.1f} MB"
                )

                st.caption(
                    f"📄 **{filename}** · {size_str} · `{content_type}` · {ago}"
                )
        else:
            st.info("No documents yet. Go to 📄 Documents to upload.")

    with col_right:
        st.subheader("Pipeline Status")
        if pipeline and "agents" in pipeline:
            agents = pipeline["agents"]
            pipeline_diagram(agents)

            # Build agent stats table
            agent_stats = [
                {
                    "name": name,
                    "status": status,
                    "avg_latency_ms": "—",
                    "total_calls": "—",
                }
                for name, status in agents.items()
            ]
            from components.pipeline_diagram import pipeline_table
            pipeline_table(agent_stats)
        else:
            st.warning("Pipeline status unavailable.")

    # ── Auto-refresh toggle ──────────────────────────────────────────────
    st.divider()
    col_refresh, _ = st.columns([1, 3])
    with col_refresh:
        auto = st.checkbox("Auto-refresh (30s)", value=False, key="dashboard_auto_refresh")
        if auto:
            st_autorefresh(interval=30000, key="dashboard_autorefresh")
