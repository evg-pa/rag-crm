"""Session state management for the RAG-CRM frontend."""

from __future__ import annotations

import streamlit as st


def init_session_state() -> None:
    """Initialize all session state variables with safe defaults."""
    defaults: dict[str, object] = {
        # — Auth —
        "auth_token": None,        # str | None — JWT access token
        "auth_user": None,         # dict | None — logged-in user profile
        # — Chat —
        "messages": [],          # list[dict] — chat history
        "history_loaded": False,
        "theme": "dark",
        # — Data caches —
        "documents_cache": None,  # list[dict] — cached document list
        "documents_cache_time": None,  # float — timestamp of last cache
        "wiki_cache": None,      # list[dict] — cached wiki entries
        "wiki_cache_time": None,  # float
        # — Pipeline —
        "pipeline_status": None,
        "pipeline_status_time": None,
        # — Health —
        "health_cache": None,    # dict — cached health response
        "health_cache_time": 0,  # float
        "health_status": None,   # dict — last health status
        # — Search —
        "last_search_query": "",
        "search_results": [],
        "search_page": 1,
        # — Navigation —
        "current_page": "dashboard",
        # — Documents / Upload —
        "scrape_url": "",        # URL input state
        "upload_success": False,  # flash message trigger
        "delete_confirm_id": None,  # document ID awaiting delete confirmation
        # — Q&A —
        "qa_top_k": 5,           # default top-k for Q&A
        "qa_session_id": "default",  # Q&A session identifier
        # — Misc —
        "app_version": "0.1.0",  # fallback app version
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def clear_chat() -> None:
    """Clear the Q&A conversation."""
    st.session_state.messages = []
    st.session_state.history_loaded = False


def invalidate_caches() -> None:
    """Invalidate all data caches (called after uploads, scrapes)."""
    st.session_state.documents_cache = None
    st.session_state.documents_cache_time = None
    st.session_state.wiki_cache = None
    st.session_state.wiki_cache_time = None


def logout() -> None:
    """Clear auth state — keeps the user on the current page."""
    st.session_state.auth_token = None
    st.session_state.auth_user = None
    invalidate_caches()
    st.rerun()


def is_authenticated() -> bool:
    """Return True if a valid auth token is present."""
    return st.session_state.get("auth_token") is not None
