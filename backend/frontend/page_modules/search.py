"""Page 4: Search — semantic + hybrid search across all documents."""

from __future__ import annotations

import streamlit as st

from components.search_result import search_results_list
from utils import api
from utils.i18n import _


def render() -> None:
    """Render the Search page."""
    st.title(_("search.title"))

    # ── Search mode selector ────────────────────────────────────────────
    col_mode, col_topk = st.columns([2, 1])
    with col_mode:
        search_mode = st.radio(
            _("search.mode"),
            options=[_("search.semantic"), _("search.hybrid")],
            horizontal=True,
            key="search_mode",
        )
    with col_topk:
        top_k = st.slider(
            _("search.top_k"),
            min_value=1,
            max_value=50,
            value=10,
            key="search_top_k",
        )

    # ── Search bar ──────────────────────────────────────────────────────
    query = st.text_input(
        "Search your documents",
        placeholder=_("search.input_placeholder"),
        key="search_query_input",
        label_visibility="collapsed",
    )

    col_search, __ = st.columns([1, 4])
    with col_search:
        search_clicked = st.button(
            _("search.btn"),
            type="primary",
            use_container_width=True,
            key="search_btn",
        )

    # ── Hybrid weight controls ──────────────────────────────────────────
    use_hybrid = "Hybrid" in search_mode
    if use_hybrid:
        col_sem, col_bm25 = st.columns(2)
        with col_sem:
            semantic_weight = st.slider(
                _("search.sem_weight"),
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.1,
                key="sem_weight",
                help=_("search.sem_weight_help"),
            )
        with col_bm25:
            bm25_weight = st.slider(
                _("search.bm25_weight"),
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.1,
                key="bm25_weight",
                help=_("search.bm25_weight_help"),
            )

    # ── Execute Search ──────────────────────────────────────────────────
    has_searched = st.session_state.get("has_searched", False)
    if not query and not search_clicked:
        if has_searched:
            st.session_state.has_searched = False
        st.info(_("search.enter_query"))
        return

    if not query.strip():
        st.warning(_("search.enter_query_warn"))
        return

    if query and (query != st.session_state.get("last_search_query") or search_clicked):
        st.session_state.last_search_query = query
        st.session_state.search_page = 1  # Reset to page 1 on new search

        with st.spinner(_("search.searching", q=query)):
            try:
                if use_hybrid:
                    results_data = api.hybrid_search(
                        query,
                        top_k=top_k,
                        semantic_weight=semantic_weight,
                        bm25_weight=bm25_weight,
                    )
                else:
                    results_data = api.semantic_search(query, top_k=top_k)

                results = results_data.get("results", [])
                st.session_state.search_results = results
                st.session_state.has_searched = True
            except Exception as exc:
                st.error(_("search.failed", err=exc))
                st.session_state.search_results = []

    # ── Render Results with Pagination ──────────────────────────────────
    results = st.session_state.get("search_results", [])
    has_searched = st.session_state.get("has_searched", False)
    if not results:
        if has_searched:
            st.warning(_("search.no_results"))
        return

    st.divider()
    mode_label = _("search.hybrid_label") if use_hybrid else _("search.semantic_label")
    st.caption(_("search.results_for", q=query, mode=mode_label, n=len(results)))

    # Pagination
    page_size = 10
    total_pages = max(1, (len(results) + page_size - 1) // page_size)
    page = st.session_state.get("search_page", 1)

    if total_pages > 1:
        page = st.number_input(
            _("search.page"),
            min_value=1,
            max_value=total_pages,
            value=page,
            key="search_page_input",
        )
        st.session_state.search_page = page

    # Render only the current page
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, len(results))
    page_results = results[start_idx:end_idx]

    search_results_list(
        page_results,
        query=query,
        page=1,  # Don't paginate inside the component; we already sliced
        page_size=page_size,
    )
