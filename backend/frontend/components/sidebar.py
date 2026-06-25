"""Sidebar navigation — nav, theme toggle, settings, and status footer."""

from __future__ import annotations

import streamlit as st


def render_sidebar() -> str:
    """Render the sidebar with navigation menu, theme toggle, settings, and status.

    Returns:
        The selected page key.
    """
    with st.sidebar:
        st.markdown(
            "<h2 style='font-size:1.1em;margin-bottom:16px;'>📄 RAG-CRM</h2>",
            unsafe_allow_html=True,
        )

        # ── Navigation ─────────────────────────────────────────────────
        selected = st.radio(
            "Navigation",
            options=[
                "📊 Dashboard",
                "📄 Documents",
                "💬 Q&A Chat",
                "🔍 Search",
                "📚 Knowledge Base",
                "🧠 Knowledge Graph",
                "📊 CRM Dashboard",
                "🔍 CRM Data",
                "💬 CRM Query",
                "🔄 CRM Sync",
                "⚙️ Pipeline",
            ],
            index=0,
            key="nav_radio",
            label_visibility="collapsed",
        )

        st.divider()

        # Theme toggle
        from utils.theme import theme_toggle

        theme_toggle()

        st.divider()

        # Top-K slider for search/Q&A
        st.caption("⚙️ Settings")
        top_k = st.slider(
            "Search Top-K",
            min_value=1,
            max_value=50,
            value=st.session_state.get("top_k", 10),
            step=1,
            key="top_k_slider",
            help="Number of chunks to retrieve for Q&A and search",
        )
        st.session_state.top_k = top_k

        st.divider()

        # Footer with system status
        health = st.session_state.get("health_status")
        if health:
            db_status = health.get("database", "?")
            status_color = "🟢" if db_status == "connected" else "🔴"
            st.caption(f"{status_color} Backend: {health.get('status', '?')}")
            st.caption(f"{'🟢' if db_status == 'connected' else '🔴'} DB: {db_status}")

        st.caption(f"v{st.session_state.get('app_version', '0.1.0')}")

    # Map display name back to page key
    page_map: dict[str, str] = {
        "📊 Dashboard": "dashboard",
        "📄 Documents": "documents",
        "💬 Q&A Chat": "qa_chat",
        "🔍 Search": "search",
        "📚 Knowledge Base": "wiki",
        "🧠 Knowledge Graph": "knowledge_graph",
        "📊 CRM Dashboard": "crm_dashboard",
        "🔍 CRM Data": "crm_data",
        "💬 CRM Query": "crm_query",
        "🔄 CRM Sync": "crm_sync",
        "⚙️ Pipeline": "pipeline",
    }
    return page_map.get(selected, "dashboard")
