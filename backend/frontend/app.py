"""RAG-CRM Streamlit Frontend — Multi-page document management + Q&A UI.

Entry point with JWT auth: if no valid token, shows the login page.
"""

from __future__ import annotations

import streamlit as st

from components.sidebar import render_sidebar
from utils.state import init_session_state, is_authenticated
from utils.theme import init_theme

# ── Page configuration (must be first Streamlit call) ───────────────────────

st.set_page_config(
    page_title="RAG-CRM",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "RAG-CRM — Hybrid RAG + CRM platform",
    },
)

# ── Initialize ─────────────────────────────────────────────────────────────

init_session_state()
init_theme()

# ── Auth check ─────────────────────────────────────────────────────────────

if not is_authenticated():
    from page_modules.login import render as render_login

    render_login()
    st.stop()  # Don't render anything below this for unauthenticated users

# ── Sidebar navigation (only shown when authenticated) ─────────────────────

current_page = render_sidebar()

# ── Route to page ──────────────────────────────────────────────────────────

if current_page == "dashboard":
    from page_modules.dashboard import render as render_dashboard

    render_dashboard()
elif current_page == "documents":
    from page_modules.documents import render as render_documents

    render_documents()
elif current_page == "qa_chat":
    from page_modules.qa_chat import render as render_qa_chat

    render_qa_chat()
elif current_page == "search":
    from page_modules.search import render as render_search

    render_search()
elif current_page == "wiki":
    from page_modules.wiki import render as render_wiki

    render_wiki()
elif current_page == "pipeline":
    from page_modules.pipeline import render as render_pipeline

    render_pipeline()
