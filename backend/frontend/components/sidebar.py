"""Sidebar navigation — nav, language selector, theme toggle, settings, and status footer."""

from __future__ import annotations

import streamlit as st

from utils.i18n import _


def render_sidebar() -> str:
    """Render the sidebar with navigation menu, language selector, theme toggle, settings, and status.

    Returns:
        The selected page key.
    """
    with st.sidebar:
        st.markdown(
            f"<h2 style='font-size:1.1em;margin-bottom:16px;'>{_('nav.title')}</h2>",
            unsafe_allow_html=True,
        )

        # ── Language selector ──────────────────────────────────────────
        lang_col1, lang_col2 = st.columns(2)
        with lang_col1:
            if st.button(
                "🇬🇧 EN",
                key="lang_en",
                use_container_width=True,
                type="secondary" if st.session_state.get("language", "en") != "en" else "primary",
            ):
                st.session_state.language = "en"
                st.rerun()
        with lang_col2:
            if st.button(
                "🇷🇺 RU",
                key="lang_ru",
                use_container_width=True,
                type="secondary" if st.session_state.get("language", "en") != "ru" else "primary",
            ):
                st.session_state.language = "ru"
                st.rerun()

        # ── Navigation ─────────────────────────────────────────────────
        selected = st.radio(
            "Navigation",
            options=[
                _("nav.dashboard"),
                _("nav.documents"),
                _("nav.qa_chat"),
                _("nav.search"),
                _("nav.wiki"),
                _("nav.knowledge_graph"),
                _("nav.crm_dashboard"),
                _("nav.crm_data"),
                _("nav.crm_query"),
                _("nav.crm_sync"),
                _("nav.pipeline"),
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
        st.caption(_("settings.title"))
        top_k = st.slider(
            _("settings.top_k"),
            min_value=1,
            max_value=50,
            value=st.session_state.get("top_k", 10),
            step=1,
            key="top_k_slider",
            help=_("settings.top_k_help"),
        )
        st.session_state.top_k = top_k

        st.divider()

        # Footer with system status
        health = st.session_state.get("health_status")
        if health:
            db_status = health.get("database", "?")
            status_color = "🟢" if db_status == "connected" else "🔴"
            st.caption(f"{status_color} {_('backend.status')}: {health.get('status', '?')}")
            st.caption(f"{'🟢' if db_status == 'connected' else '🔴'} {_('db.status')}: {db_status}")
            # LLM info
            llm_model = health.get("llm_model", "?")
            llm_url = health.get("llm_base_url", "?")
            llm_configured = health.get("llm_configured", False)
            llm_icon = "🟢" if llm_configured else "🟡"
            # Provider name from URL or model
            if llm_url and llm_url != "?":
                try:
                    provider = llm_url.split("//")[-1].split(".")[0].capitalize()
                except Exception:
                    provider = "?"
            else:
                provider = "?"
            st.caption(f"{llm_icon} LLM: {llm_model} · {provider}")

        st.caption(f"v{st.session_state.get('app_version', '0.1.0')}")

    # Map display name back to page key
    page_map: dict[str, str] = {
        _("nav.dashboard"): "dashboard",
        _("nav.documents"): "documents",
        _("nav.qa_chat"): "qa_chat",
        _("nav.search"): "search",
        _("nav.wiki"): "wiki",
        _("nav.knowledge_graph"): "knowledge_graph",
        _("nav.crm_dashboard"): "crm_dashboard",
        _("nav.crm_data"): "crm_data",
        _("nav.crm_query"): "crm_query",
        _("nav.crm_sync"): "crm_sync",
        _("nav.pipeline"): "pipeline",
    }
    return page_map.get(selected, "dashboard")
