"""RAG-CRM Streamlit Frontend — Multi-page document management + Q&A UI.

Open to all users (no authentication required).
"""

from __future__ import annotations

import streamlit as st

from components.sidebar import render_sidebar
from utils.state import init_session_state
from utils.theme import init_theme
from utils.i18n import _

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
elif current_page == "crm_dashboard":
    from page_modules.crm_dashboard import render as render_crm_dashboard

    render_crm_dashboard()
elif current_page == "crm_data":
    from page_modules.crm_data import render as render_crm_data

    render_crm_data()
elif current_page == "crm_query":
    from page_modules.crm_query import render as render_crm_query

    render_crm_query()
elif current_page == "crm_sync":
    from page_modules.crm_sync import render as render_crm_sync

    render_crm_sync()
elif current_page == "knowledge_graph":
    from page_modules.knowledge_graph import render as render_knowledge_graph

    render_knowledge_graph()
elif current_page == "pipeline":
    from page_modules.pipeline import render as render_pipeline

    render_pipeline()
