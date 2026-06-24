"""Page 4: Search — semantic + hybrid search across all documents."""

from __future__ import annotations

import streamlit as st

from components.search_result import search_results_list
from utils import api


def render() -> None:
    """Render the Search page."""
    st.title("🔍 Search")

    # ── Search mode selector ────────────────────────────────────────────
    col_mode, col_topk = st.columns([2, 1])
    with col_mode:
        search_mode = st.radio(
            "Search mode",
            options=["Semantic (embedding)", "Hybrid (semantic + BM25 + reranker)"],
            horizontal=True,
            key="search_mode",
        )
    with col_topk:
        top_k = st.slider(
            "Top-K",
            min_value=1,
            max_value=50,
            value=10,
            key="search_top_k",
        )

    # ── Search bar ──────────────────────────────────────────────────────
    query = st.text_input(
        "Search your documents",
        placeholder="Enter your search query...",
        key="search_query_input",
        label_visibility="collapsed",
    )

    col_search, _ = st.columns([1, 4])
    with col_search:
        search_clicked = st.button(
            "🔍 Search",
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
                "Semantic weight",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.1,
                key="sem_weight",
                help="Weight for semantic (embedding) score in fusion",
            )
        with col_bm25:
            bm25_weight = st.slider(
                "BM25 weight",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.1,
                key="bm25_weight",
                help="Weight for BM25 keyword score in fusion",
            )

    # ── Execute Search ──────────────────────────────────────────────────
    if not query and not search_clicked:
        st.info("Enter a query above and click Search.")
        return

    if not query.strip():
        st.warning("Please enter a search query.")
        return

    if query != st.session_state.get("last_search_query") or search_clicked:
        st.session_state.last_search_query = query
        st.session_state.search_page = 1  # Reset to page 1 on new search

        with st.spinner(f"🔍 Searching: **{query}**"):
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
            except Exception as exc:
                st.error(f"❌ Search failed: {exc}")
                st.session_state.search_results = []

    # ── Render Results with Pagination ──────────────────────────────────
    results = st.session_state.get("search_results", [])
    if not results:
        st.caption("No results found.")
        return

    st.divider()
    mode_label = "Hybrid search" if use_hybrid else "Semantic search"
    st.caption(f"Results for **{query}** — {mode_label} ({len(results)} total)")

    # Pagination
    page_size = 10
    total_pages = max(1, (len(results) + page_size - 1) // page_size)
    page = st.session_state.get("search_page", 1)

    if total_pages > 1:
        page = st.number_input(
            "Page",
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
