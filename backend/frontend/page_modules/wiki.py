"""Page 5: Knowledge Base — browse auto-generated wiki entries."""

from __future__ import annotations

import streamlit as st

from utils import api, state


def render() -> None:
    """Render the Knowledge Base (Wiki) page."""
    st.title("📚 Knowledge Base")
    st.caption("Auto-generated summaries from your documents via the LLM Knowledge Agent.")

    # ── Search bar ──────────────────────────────────────────────────────
    wiki_search = st.text_input(
        "Search wiki entries",
        placeholder="Search by keyword or topic...",
        key="wiki_search_input",
        label_visibility="collapsed",
    )

    # ── Refresh button ──────────────────────────────────────────────────
    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Refresh", key="refresh_wiki"):
            state.invalidate_caches()
            st.rerun()

    # ── Fetch entries ───────────────────────────────────────────────────
    try:
        if wiki_search.strip():
            entries = api.search_wiki(wiki_search.strip())
            st.caption(f"Search results for **{wiki_search}**: {len(entries)} found")
        else:
            wiki_data = api.list_wiki_entries(page=1, page_size=50)
            entries = wiki_data.get("entries", [])
            total = wiki_data.get("total", 0)
            st.caption(f"{total} entries")
    except Exception as exc:
        st.error(f"❌ Failed to load wiki entries: {exc}")
        entries = []

    # ── Display entries ─────────────────────────────────────────────────
    if not entries:
        st.info(
            "No wiki entries yet. Upload documents and the Knowledge Agent "
            "will auto-generate summaries. Click 🔄 Refresh to check again."
        )
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
                st.markdown(f"**📋 Document Summary**")
                st.caption(f"Document: `{doc_id[:12]}...` · Updated: {updated[:10]}")

            with col_btn:
                if st.button("🔄 Regenerate", key=f"regen_{doc_id}", use_container_width=True):
                    with st.spinner("Regenerating wiki entry..."):
                        try:
                            api.refresh_wiki_entry(doc_id)
                            st.toast("✅ Regenerated!", icon="✅")
                            state.invalidate_caches()
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to regenerate: {exc}")

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
            with st.expander("📄 View full summary", expanded=False):
                st.markdown(summary)
