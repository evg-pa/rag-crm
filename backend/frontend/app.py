"""RAG-CRM Streamlit Frontend — Multi-page document management + Q&A UI.

Entry point using st.navigation (Streamlit ≥ 1.40).
"""

from __future__ import annotations

import streamlit as st

from components.sidebar import render_sidebar
from utils.state import init_session_state
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

# ── Sidebar navigation ─────────────────────────────────────────────────────

current_page = render_sidebar()

# ── Route to page ──────────────────────────────────────────────────────────

if current_page == "dashboard":
    from pages.dashboard import render as render_dashboard
    render_dashboard()
elif current_page == "documents":
    from pages.documents import render as render_documents
    render_documents()
elif current_page == "qa_chat":
    from pages.qa_chat import render as render_qa_chat
    render_qa_chat()
elif current_page == "search":
    from pages.search import render as render_search
    render_search()
elif current_page == "wiki":
    from pages.wiki import render as render_wiki
    render_wiki()
elif current_page == "pipeline":
    from pages.pipeline import render as render_pipeline
    render_pipeline()
