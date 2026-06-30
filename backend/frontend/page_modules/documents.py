"""Page 2: Documents — upload, scrape, browse, and manage documents."""

from __future__ import annotations

import streamlit as st

from components.document_card import delete_confirm_dialog, document_card, document_grid
from utils import api, state
from utils.i18n import _


def _handle_upload(uploaded_files) -> None:
    """Process uploaded files."""
    if not uploaded_files:
        return

    success_count = 0
    fail_count = 0

    for uploaded_file in uploaded_files:
        try:
            file_bytes = uploaded_file.read()
            result = api.upload_document(file_bytes, uploaded_file.name)
            chunk_count = result.get("chunk_count", 0)
            success_count += 1
            st.toast(
                _("documents.uploaded_ok", name=uploaded_file.name, n=chunk_count),
                icon="✅",
            )
        except Exception as exc:
            fail_count += 1
            st.toast(_("documents.upload_fail", name=uploaded_file.name, err=exc), icon="❌")

    if success_count > 0:
        state.invalidate_caches()

    if fail_count == 0 and success_count > 0:
        st.session_state.upload_success = True


def _handle_scrape(url: str) -> None:
    """Scrape a URL and ingest its content."""
    if not url.strip():
        st.warning(_("documents.url_hint"))
        return

    try:
        result = api.scrape_url(url.strip())
        chunk_count = result.get("chunk_count", 0)
        title = result.get("page_title", "Untitled")
        st.toast(
            _("documents.scraped_ok", title=title, n=chunk_count),
            icon="🌐",
        )
        state.invalidate_caches()
    except Exception as exc:
        st.error(_("documents.scrape_fail", err=exc))


def _handle_delete(document_id: str) -> None:
    """Delete a document via the backend API."""
    try:
        result = api.delete_document(document_id)
        st.toast(_("documents.del_ok", status=result.get("status", "ok")), icon="🗑️")
        state.invalidate_caches()
    except Exception as exc:
        st.error(_("documents.del_fail", err=exc))
    st.session_state.delete_confirm_id = None


def render() -> None:
    """Render the Documents page."""
    st.title(_("documents.title"))

    # ── Upload Section ──────────────────────────────────────────────────
    with st.container(border=True):
        st.subheader(_("documents.upload"))

        uploaded_files = st.file_uploader(
            _("documents.choose_files"),
            type=["pdf", "docx", "html", "htm", "md", "txt"],
            accept_multiple_files=True,
            key="doc_uploader",
        )

        if uploaded_files:
            if st.button(_("documents.upload_btn"), type="primary", use_container_width=True):
                _handle_upload(uploaded_files)

        st.caption(_("documents.supported"))

    # ── URL Scrape Section ──────────────────────────────────────────────
    with st.container(border=True):
        st.subheader(_("documents.scrape"))

        col_url, col_btn = st.columns([3, 1])
        with col_url:
            url_input = st.text_input(
                _("documents.url"),
                placeholder="https://example.com/page",
                key="scrape_url_input",
            )
        with col_btn:
            if st.button(_("documents.scrape_btn"), use_container_width=True, key="scrape_btn"):
                with st.spinner(_("documents.scraping")):
                    _handle_scrape(url_input)

    # ── Document List ───────────────────────────────────────────────────
    st.divider()
    st.subheader(_("documents.all_docs"))

    # Refresh button
    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button(_("documents.refresh"), key="refresh_docs"):
            state.invalidate_caches()
            st.rerun()

    docs = api.list_documents()
    if docs:
        st.session_state.documents_cache = docs

    # Delete confirmation
    confirmed_delete = delete_confirm_dialog()
    if confirmed_delete:
        _handle_delete(confirmed_delete)
        st.rerun()

    # Document grid
    selected_id = document_grid(docs or [], cols=3)

    # Show detail view if a document is selected
    if selected_id:
        st.divider()
        try:
            doc_detail = api.get_document(selected_id)
            document_card(doc_detail, on_view=True)
        except Exception as exc:
            st.error(f"Failed to load document detail: {exc}")
