"""Search result components — result cards and paginated lists."""

from __future__ import annotations

import streamlit as st

CONTENT_TYPE_ICONS: dict[str, str] = {
    "application/pdf": "📄",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "📝",
    "text/html": "🌐",
    "text/markdown": "📋",
    "text/plain": "📃",
}


def content_type_icon(content_type: str) -> str:
    """Return an emoji icon for a content type."""
    return CONTENT_TYPE_ICONS.get(content_type, "📎")


def _relevance_color(score: float) -> str:
    """Return a CSS color for a relevance score."""
    if score >= 0.8:
        return "var(--success)"
    if score >= 0.5:
        return "var(--warning)"
    return "var(--text-secondary)"


def search_result_card(result: dict, index: int, query: str = "") -> None:
    """Render a single search result card.

    Args:
        result: Search result dict.
        index: Result index for display.
        query: Original search query (for highlighting context).
    """
    similarity = result.get("similarity", result.get("hybrid_score", 0.0))
    content = result.get("content", "")
    doc_id = result.get("document_id", "unknown")
    chunk_idx = result.get("chunk_index", "?")
    color = _relevance_color(similarity)

    # Show additional scores for hybrid results
    extra_scores = ""
    if "bm25_score" in result:
        extra_scores = (
            f" · BM25: {result.get('bm25_score', 0):.3f}"
            f" · Reranker: {result.get('reranker_score', 0) or 'N/A'}"
        )

    with st.container():
        st.markdown(
            f"""
            <div class="rag-card rag-result-card" style="border-left-color: {color};">
                <strong>📄 Chunk #{chunk_idx}</strong>
                &nbsp;
                <span class="result-score" style="color: {color};">{similarity:.3f}</span>
                <small style="color: var(--text-secondary);">{extra_scores}</small>
                <br>
                <small style="color: var(--text-secondary);">doc: {doc_id[:12]}…</small>
                <p style="margin-top: 8px; font-size: 0.9rem;">{content[:300]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("Show full excerpt", expanded=False):
            st.text(content)


def search_results_list(
    results: list[dict],
    query: str = "",
    page: int = 1,
    page_size: int = 10,
) -> tuple[int, list[dict]]:
    """Render a paginated list of search results.

    Args:
        results: Full list of search result dicts.
        query: Original search query.
        page: Current page number (1-indexed).
        page_size: Results per page.

    Returns:
        Tuple of (total_pages, page_results).
    """
    total = len(results)
    total_pages = max(1, (total + page_size - 1) // page_size)

    start = (page - 1) * page_size
    end = min(start + page_size, total)
    page_results = results[start:end]

    if not page_results:
        st.info("No results found.")
        return total_pages, []

    for i, result in enumerate(page_results):
        search_result_card(result, start + i + 1, query=query)

    st.caption(f"Showing {start + 1}–{end} of {total} results · Page {page} of {total_pages}")

    return total_pages, page_results
