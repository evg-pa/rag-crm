"""Theme management — sophisticated dark/light theme with rich styling."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_STATIC_DIR = Path(__file__).parent.parent / "static"


def load_css() -> None:
    """Inject global custom CSS from static/style.css."""
    css_path = _STATIC_DIR / "style.css"
    if css_path.exists():
        css_content = css_path.read_text()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)


def _global_base() -> str:
    """Base resets and shared styles — applied regardless of theme."""
    return """
    <style>
    /* ── Typography — system font stack ── */
    html, body, [class*="css"]  {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                     Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', Arial,
                     sans-serif;
    }

    /* ── Hide Streamlit chrome ── */
    header[data-testid="stHeader"] { background: transparent !important; }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }

    /* ── Smooth transitions ── */
    .stApp, section[data-testid="stSidebar"],
    .stButton button, .stTextInput input, .stSelectbox,
    div[data-testid="stFileUploader"] {
        transition: background-color 0.3s ease, border-color 0.3s ease,
                    box-shadow 0.3s ease, color 0.3s ease;
    }

    /* ── Buttons ── */
    .stButton button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1.2rem !important;
        border: 1px solid transparent !important;
    }
    .stButton button[kind="primary"] {
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
    }
    .stButton button[kind="primary"]:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
    }
    .stButton button[kind="secondary"]:hover {
        border-color: var(--accent) !important;
    }

    /* ── Text inputs ── */
    .stTextInput input {
        border-radius: 8px !important;
        padding: 0.6rem 0.9rem !important;
        font-size: 0.95rem !important;
    }
    .stTextInput input:focus {
        box-shadow: 0 0 0 3px var(--focus-ring) !important;
        border-color: var(--accent) !important;
    }

    /* ── File uploader ── */
    div[data-testid="stFileUploader"] {
        border-radius: 10px !important;
        padding: 0.5rem !important;
    }
    div[data-testid="stFileUploader"] section {
        border: 2px dashed var(--border) !important;
        border-radius: 10px !important;
        padding: 2rem 1rem !important;
    }
    div[data-testid="stFileUploader"] section:hover {
        border-color: var(--accent) !important;
        background: var(--hover-overlay) !important;
    }

    /* ── Tabs ── */
    button[data-baseweb="tab"] {
        border-radius: 8px 8px 0 0 !important;
        font-weight: 500 !important;
    }

    /* ── Slider ── */
    div[data-testid="stSlider"] {
        padding: 0.3rem 0 !important;
    }

    /* ── Dividers ── */
    hr {
        margin: 1.2rem 0 !important;
        border-color: var(--border) !important;
    }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        border-radius: 8px !important;
        font-weight: 500 !important;
    }

    /* ── Metric / KPI ── */
    div[data-testid="metric-container"] {
        border-radius: 10px !important;
        padding: 1rem 0.8rem !important;
        border: 1px solid var(--border) !important;
        background: var(--bg-secondary) !important;
    }

    /* ── Spinner ── */
    .stSpinner {
        text-align: center;
        padding: 2rem 0;
    }

    /* ── Code blocks ── */
    code {
        border-radius: 4px !important;
        padding: 0.15em 0.4em !important;
    }
    pre {
        border-radius: 10px !important;
        padding: 1rem !important;
    }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: transparent;
    }
    ::-webkit-scrollbar-thumb {
        background: var(--border);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-secondary);
    }
    </style>
    """


def _dark_css() -> str:
    """Rich dark theme — deep navy-charcoal with warm indigo accent."""
    return """
    <style>
    :root {
        --bg-primary: #0F1419;
        --bg-secondary: #1A1F2B;
        --bg-tertiary: #242B3D;
        --text-primary: #E8EDF5;
        --text-secondary: #8892A8;
        --accent: #6C63FF;
        --accent-hover: #5A52E0;
        --accent-soft: rgba(108, 99, 255, 0.12);
        --success: #34D399;
        --warning: #FBBF24;
        --error: #F87171;
        --border: #2D3548;
        --focus-ring: rgba(108, 99, 255, 0.25);
        --hover-overlay: rgba(255, 255, 255, 0.04);
    }
    .stApp {
        background-color: var(--bg-primary);
    }
    section[data-testid="stSidebar"] {
        background-color: var(--bg-secondary);
        border-right: 1px solid var(--border);
    }
    /* Sidebar radio items */
    section[data-testid="stSidebar"] label {
        padding: 0.4rem 0.8rem !important;
        border-radius: 6px !important;
        margin: 2px 0 !important;
        transition: background 0.15s ease !important;
    }
    section[data-testid="stSidebar"] label:hover {
        background: var(--hover-overlay) !important;
    }
    section[data-testid="stSidebar"] label[data-selected="true"] {
        background: var(--accent-soft) !important;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 2px !important;
    }
    /* Containers / cards */
    div[data-testid="stVerticalBlockBorderWrapper"] > div,
    section[data-testid="stFileUploader"] section {
        border-radius: 10px !important;
    }
    .stButton button[kind="primary"] {
        background: var(--accent) !important;
        color: white !important;
    }
    .stButton button[kind="primary"]:hover {
        background: var(--accent-hover) !important;
    }
    .stButton button[kind="secondary"] {
        background: transparent !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border) !important;
    }
    .stButton button[kind="secondary"]:hover {
        border-color: var(--accent) !important;
        background: var(--accent-soft) !important;
    }
    .stTextInput input {
        background: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border) !important;
    }
    .stTextInput input::placeholder {
        color: var(--text-secondary) !important;
        opacity: 0.7;
    }
    div[data-testid="stFileUploader"] {
        background: transparent !important;
    }
    div[data-testid="stFileUploader"] section {
        background: var(--bg-tertiary) !important;
        border-color: var(--border) !important;
    }
    .st-bb, .st-at, .st-au, .st-ae, .st-af {
        background-color: var(--bg-tertiary) !important;
        border-color: var(--border) !important;
        color: var(--text-primary) !important;
    }
    /* Select boxes */
    div[data-baseweb="select"] > div {
        background: var(--bg-tertiary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }
    /* Dataframe / table */
    .stDataFrame {
        border-radius: 10px !important;
        overflow: hidden !important;
    }
    .stDataFrame [data-testid="StyledDataFrameColHeader"] {
        background: var(--bg-tertiary) !important;
    }
    /* Toast */
    div[data-testid="stToast"] {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4) !important;
    }
    </style>
    """


def _light_css() -> str:
    """Crisp light theme — high contrast, clean structure, bold accents."""
    return """
    <style>
    :root {
        --bg-primary: #EFF1F5;
        --bg-secondary: #FFFFFF;
        --bg-tertiary: #E5E7EB;
        --text-primary: #0F172A;
        --text-secondary: #475569;
        --accent: #4F46E5;
        --accent-hover: #4338CA;
        --accent-soft: rgba(79, 70, 229, 0.1);
        --success: #059669;
        --warning: #D97706;
        --error: #DC2626;
        --border: #CBD5E1;
        --focus-ring: rgba(79, 70, 229, 0.25);
        --hover-overlay: rgba(0, 0, 0, 0.05);
    }
    .stApp {
        background-color: var(--bg-primary);
    }
    section[data-testid="stSidebar"] {
        background-color: var(--bg-secondary);
        border-right: 1px solid var(--border);
    }
    section[data-testid="stSidebar"] label {
        padding: 0.4rem 0.8rem !important;
        border-radius: 6px !important;
        margin: 2px 0 !important;
        transition: background 0.15s ease !important;
        color: var(--text-primary) !important;
    }
    section[data-testid="stSidebar"] label:hover {
        background: var(--hover-overlay) !important;
    }
    section[data-testid="stSidebar"] label[data-selected="true"] {
        background: var(--accent-soft) !important;
        font-weight: 600 !important;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 2px !important;
    }
    .stButton button[kind="primary"] {
        background: var(--accent) !important;
        color: white !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
        font-weight: 600 !important;
    }
    .stButton button[kind="primary"]:hover {
        background: var(--accent-hover) !important;
        box-shadow: 0 4px 14px rgba(79,70,229,0.3) !important;
    }
    .stButton button[kind="secondary"] {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border) !important;
        font-weight: 500 !important;
    }
    .stButton button[kind="secondary"]:hover {
        border-color: var(--accent) !important;
        background: var(--accent-soft) !important;
    }
    .stTextInput input {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1.5px solid var(--border) !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    .stTextInput input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--focus-ring) !important;
    }
    .stTextInput input::placeholder {
        color: var(--text-secondary) !important;
        opacity: 0.6;
    }
    div[data-testid="stFileUploader"] {
        background: transparent !important;
    }
    div[data-testid="stFileUploader"] section {
        background: var(--bg-primary) !important;
        border: 2px dashed var(--border) !important;
    }
    div[data-testid="stFileUploader"] section:hover {
        border-color: var(--accent) !important;
        background: var(--accent-soft) !important;
    }
    .st-bb, .st-at, .st-au, .st-ae, .st-af {
        background-color: var(--bg-secondary) !important;
        border-color: var(--border) !important;
        color: var(--text-primary) !important;
    }
    div[data-baseweb="select"] > div {
        background: var(--bg-secondary) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 8px !important;
    }
    div[data-testid="stToast"] {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.15) !important;
    }
    hr {
        border-color: var(--border) !important;
        opacity: 0.7;
    }
    div[data-testid="metric-container"] {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
    }
    .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2,
    .stMarkdown h3, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
        color: var(--text-primary) !important;
    }
    .stCaption, .st-emotion-caption {
        color: var(--text-secondary) !important;
    }
    .stDataFrame {
        border-radius: 10px !important;
        overflow: hidden !important;
        border: 1px solid var(--border) !important;
    }
    </style>
    """


def init_theme() -> None:
    """Initialize theme in session state and inject CSS."""
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    # Global base styles + theme-specific overrides
    st.markdown(_global_base(), unsafe_allow_html=True)

    if st.session_state.theme == "dark":
        st.markdown(_dark_css(), unsafe_allow_html=True)
    else:
        st.markdown(_light_css(), unsafe_allow_html=True)


def theme_toggle() -> None:
    """Render a theme toggle button and handle switching."""
    current = st.session_state.get("theme", "dark")
    label = "🌙 Dark" if current == "dark" else "☀️ Light"
    if st.button(label, key="theme_toggle_btn"):
        st.session_state.theme = "light" if current == "dark" else "dark"
        st.rerun()
