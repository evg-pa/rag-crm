"""Document card and grid components."""

from __future__ import annotations

import streamlit as st

from components.search_result import content_type_icon


def document_card(doc: dict, on_view: bool = False) -> None:
    """Render a single document detail card.

    Args:
        doc: Document dict from the API (with chunks for detail view).
        on_view: If True, renders full detail view instead of compact card.
    """
    filename = doc.get("filename", "unknown")
    content_type = doc.get("content_type", "")
    file_size = doc.get("file_size", 0)
    doc_id = doc.get("id", "")

    size_str = (
        f"{file_size / 1024:.1f} KB"
        if file_size < 1024 * 1024
        else f"{file_size / (1024 * 1024):.1f} MB"
    )
    icon = content_type_icon(content_type)

    if on_view:
        # Full detail view
        st.markdown(f"### {icon} {filename}")
        st.caption(f"ID: `{doc_id}` · Type: `{content_type}` · Size: {size_str}")

        metadata = doc.get("metadata") or {}
        if metadata:
            with st.expander("📋 Metadata", expanded=False):
                st.json(metadata)

        chunks = doc.get("chunks", [])
        if chunks:
            st.markdown(f"**🧩 Chunks** ({len(chunks)})")
            for chunk in chunks:
                idx = chunk.get("chunk_index", "?")
                content = chunk.get("content", "")
                with st.expander(f"Chunk #{idx} — {content[:60]}…", expanded=False):
                    st.text(content)
    else:
        # Compact card
        st.markdown(
            f"""
            <div class="rag-card rag-doc-card">
                <div class="doc-icon">{icon}</div>
                <div class="doc-filename">{filename[:50]}</div>
                <div class="doc-meta">{size_str} · {content_type.split('/')[-1]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def document_grid(docs: list[dict], cols: int = 3) -> str | None:
    """Render a grid of document cards.

    Args:
        docs: List of document dicts.
        cols: Number of columns in the grid.

    Returns:
        The ID of the selected document, or None.
    """
    if not docs:
        st.info("No documents found.")
        return None

    selected_id: str | None = None
    columns = st.columns(cols)

    for i, doc in enumerate(docs):
        with columns[i % cols]:
            filename = doc.get("filename", "unknown")
            content_type = doc.get("content_type", "")
            file_size = doc.get("file_size", 0)
            doc_id = doc.get("id", "")

            size_str = (
                f"{file_size / 1024:.1f} KB"
                if file_size < 1024 * 1024
                else f"{file_size / (1024 * 1024):.1f} MB"
            )
            icon = content_type_icon(content_type)

            st.markdown(
                f"""
                <div class="rag-card rag-doc-card">
                    <div class="doc-icon">{icon}</div>
                    <div class="doc-filename">{filename[:40]}</div>
                    <div class="doc-meta">{size_str}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔍 View", key=f"view_{doc_id}", use_container_width=True):
                    selected_id = doc_id
            with c2:
                if st.button("🗑️ Del", key=f"del_{doc_id}", use_container_width=True):
                    st.session_state.delete_confirm_id = doc_id

    return selected_id


def delete_confirm_dialog() -> str | None:
    """Show a delete confirmation dialog if a document is pending deletion.

    Returns:
        The document ID to delete if confirmed, None otherwise.
    """
    doc_id = st.session_state.get("delete_confirm_id")
    if not doc_id:
        return None

    # Show confirmation
    st.warning(f"⚠️ Are you sure you want to delete document `{doc_id[:12]}…`?")

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("✅ Yes, delete", key="confirm_del", type="primary", use_container_width=True):
            st.session_state.delete_confirm_id = None
            return doc_id
    with col_no:
        if st.button("❌ Cancel", key="cancel_del", use_container_width=True):
            st.session_state.delete_confirm_id = None
            return None

    return None
