"""Page 5: Knowledge Base — browse auto-generated wiki entries."""

from __future__ import annotations

import streamlit as st

from utils import api, state
from utils.i18n import _


def render() -> None:
    """Render the Knowledge Base (Wiki) page."""
    st.title(_("wiki.title"))
    st.caption(_("wiki.caption"))

    # ── Search bar ──────────────────────────────────────────────────────
    wiki_search = st.text_input(
        _("wiki.search_label"),
        placeholder=_("wiki.search_placeholder"),
        key="wiki_search_input",
        label_visibility="collapsed",
    )

    # ── Refresh button ──────────────────────────────────────────────────
    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button(_("wiki.refresh"), key="refresh_wiki"):
            state.invalidate_caches()
            st.rerun()

    # ── Fetch entries ───────────────────────────────────────────────────
    try:
        if wiki_search.strip():
            entries = api.search_wiki(wiki_search.strip())
            st.caption(_("wiki.results_for", q=wiki_search, n=len(entries)))
        else:
            wiki_data = api.list_wiki_entries(page=1, page_size=50)
            entries = wiki_data.get("entries", [])
            total = wiki_data.get("total", 0)
            st.caption(_("wiki.n_entries", n=total))
    except Exception as exc:
        st.error(_("wiki.load_failed", err=exc))
        entries = []

    # ── Display entries ─────────────────────────────────────────────────
    if not entries:
        st.info(_("wiki.empty"))
        return

    for entry in entries:
        doc_id = entry.get("document_id", "unknown")
        summary = entry.get("summary", "No summary available.")
        topics = entry.get("topics", [])
        updated = entry.get("updated_at", "")
        created = entry.get("created_at", "")

        # Truncate summary for preview
        preview = summary[:300] + ("..." if len(summary) > 300 else "")

        with st.container(border=True):
            # Header row
            col_info, col_btn = st.columns([3, 1])
            with col_info:
                st.markdown(_("wiki.doc_summary"))
                st.caption(_("wiki.doc_info", id=doc_id[:12], date=updated[:10]))

            with col_btn:
                if st.button(_("wiki.regenerate"), key=f"regen_{doc_id}", use_container_width=True):
                    with st.spinner(_("wiki.regenerating")):
                        try:
                            api.refresh_wiki_entry(doc_id)
                            st.toast(_("wiki.regenerated"), icon="✅")
                            state.invalidate_caches()
                            st.rerun()
                        except Exception as exc:
                            st.error(_("wiki.regenerate_fail", err=exc))

            # Topics as tags
            if topics:
                tags_html = " ".join(
                    f'<span class="rag-wiki-tag">{topic}</span>'
                    for topic in topics
                )
                st.markdown(
                    f'<div class="wiki-topics">{tags_html}</div>',
                    unsafe_allow_html=True,
                )

            # Summary preview + expand
            with st.expander(_("wiki.view_full"), expanded=False):
                st.markdown(summary)
