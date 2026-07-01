"""Sidebar navigation — nav, language selector, theme toggle, settings, LLM config, and status footer."""

from __future__ import annotations

import streamlit as st

from utils.i18n import _
from utils import api


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

            # ── LLM config expander ──────────────────────────────────────
            llm_model = health.get("llm_model", "?")
            llm_url = health.get("llm_base_url", "?")
            llm_configured = health.get("llm_configured", False)
            llm_icon = "🟢" if llm_configured else "🟡"
            if llm_url and llm_url != "?":
                try:
                    provider_name = llm_url.split("//")[-1].split(".")[0].capitalize()
                except Exception:
                    provider_name = "?"
            else:
                provider_name = "?"
            st.caption(f"{llm_icon} LLM: {llm_model} · {provider_name}")

            # Fetch current runtime config for the form
            try:
                llm_cfg = api.get_llm_config()
            except Exception:
                llm_cfg = {}

            with st.expander("⚙️ Change LLM", expanded=False):
                # Provider selector
                provider_keys = list(api.PROVIDER_PRESETS.keys())
                current_preset = llm_cfg.get("llm_base_url", llm_url)
                default_idx = 0
                for i, (k, v) in enumerate(api.PROVIDER_PRESETS.items()):
                    if v.get("base_url") and current_preset and v["base_url"].rstrip("/") == current_preset.rstrip("/"):
                        default_idx = i
                        break

                sel_provider = st.selectbox(
                    "Provider",
                    options=provider_keys,
                    index=default_idx,
                    key="llm_provider_sel",
                )

                is_ollama = sel_provider == "Ollama (local)"
                is_custom = sel_provider == "Custom"
                preset = api.PROVIDER_PRESETS[sel_provider]

                # Base URL
                default_url = preset["base_url"] if not is_custom else (llm_cfg.get("llm_base_url") or llm_url)
                new_url = st.text_input(
                    "Base URL",
                    value=default_url,
                    key="llm_url_input",
                    disabled=not is_custom and not is_ollama,
                )

                # Model
                default_model = preset["model"] if not is_custom else (llm_cfg.get("llm_model") or llm_model)
                new_model = st.text_input(
                    "Model",
                    value=default_model,
                    key="llm_model_input",
                    disabled=not is_custom and not is_ollama,
                )

                # API Key (hidden for Ollama)
                new_key = ""
                if not is_ollama:
                    display_key = llm_cfg.get("llm_api_key", "")
                    new_key = st.text_input(
                        "API Key",
                        value="" if display_key and "..." in str(display_key) else display_key,
                        type="password",
                        placeholder="sk-..." if not display_key else "•••••••",
                        key="llm_key_input",
                    )

                # Apply button
                col_apply, col_test = st.columns(2)
                with col_apply:
                    if st.button("✅ Apply", use_container_width=True, key="llm_apply_btn"):
                        with st.spinner("Applying..."):
                            try:
                                api.update_llm_config(
                                    llm_api_key=new_key,
                                    llm_base_url=new_url,
                                    llm_model=new_model,
                                )
                                # Refresh health
                                health = api.health_check()
                                st.session_state.health_status = health
                                st.session_state.health_cache = health
                                st.session_state.health_cache_time = __import__("time").time()
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Failed: {exc}")

                with col_test:
                    if st.button("🔍 Test", use_container_width=True, key="llm_test_btn"):
                        test_key = new_key or llm_cfg.get("llm_api_key", "")
                        with st.spinner("Testing..."):
                            result = api.test_llm_connection(
                                api_key=test_key,
                                base_url=new_url,
                                model=new_model,
                            )
                            if result.get("status") == "ok":
                                st.success("✅ " + result.get("message", "OK"))
                            else:
                                st.error("❌ " + result.get("message", "Failed"))

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
