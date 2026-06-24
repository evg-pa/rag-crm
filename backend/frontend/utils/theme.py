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
    /* Typography — system font stack */
    html, body, [class*="css"]  {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                     Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', Arial,
                     sans-serif;
    }

    /* Hide Streamlit chrome */
    header[data-testid="stHeader"] { background: transparent !important; }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }

    /* Smooth transitions */
    .stApp, section[data-testid="stSidebar"],
    .stButton button, .stTextInput input, .stSelectbox,
    div[data-testid="stFileUploader"] {
        transition: background-color 0.3s ease, border-color 0.3s ease,
                    box-shadow 0.3s ease, color 0.3s ease;
    }

    /* Buttons */
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

    /* Text inputs */
    .stTextInput input {
        border-radius: 8px !important;
        padding: 0.6rem 0.9rem !important;
        font-size: 0.95rem !important;
    }
    .stTextInput input:focus {
        box-shadow: 0 0 0 3px var(--focus-ring) !important;
        border-color: var(--accent) !important;
    }

    /* File uploader */
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

    /* Tabs */
    button[data-baseweb="tab"] {
        border-radius: 8px 8px 0 0 !important;
        font-weight: 500 !important;
    }

    /* Slider */
    div[data-testid="stSlider"] {
        padding: 0.3rem 0 !important;
    }

    /* Dividers */
    hr {
        margin: 1.2rem 0 !important;
        border-color: var(--border) !important;
    }

    /* Expander */
    .streamlit-expanderHeader {
        border-radius: 8px !important;
        font-weight: 500 !important;
    }

    /* Metric / KPI */
    div[data-testid="metric-container"] {
        border-radius: 10px !important;
        padding: 1rem 0.8rem !important;
        border: 1px solid var(--border) !important;
        background: var(--bg-secondary) !important;
    }

    /* Spinner */
    .stSpinner {
        text-align: center;
        padding: 2rem 0;
    }

    /* Code blocks */
    code {
        border-radius: 4px !important;
        padding: 0.15em 0.4em !important;
    }
    pre {
        border-radius: 10px !important;
        padding: 1rem !important;
    }

    /* Scrollbar */
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
    """High-contrast light theme — crisp, bold, every element visible."""
    return """
    <style>
    :root {
        --bg-primary: #F3F4F8;
        --bg-secondary: #FFFFFF;
        --bg-tertiary: #E5E7EC;
        --text-primary: #0B0D14;
        --text-secondary: #3D4455;
        --accent: #4F46E5;
        --accent-hover: #3730A3;
        --accent-soft: rgba(79, 70, 229, 0.10);
        --success: #059669;
        --warning: #D97706;
        --error: #DC2626;
        --border: #B0B8C8;
        --focus-ring: rgba(79, 70, 229, 0.30);
        --hover-overlay: rgba(0, 0, 0, 0.06);
    }
    /* Use dark for sidebar toggle button label color */
    section[data-testid="stSidebar"] .stButton button {
        color: var(--text-primary) !important;
    }
    /* Main background */
    .stApp {
        background-color: var(--bg-primary) !important;
    }
    section[data-testid="stSidebar"] {
        background-color: var(--bg-secondary) !important;
        border-right: 1.5px solid var(--border) !important;
    }
    section[data-testid="stSidebar"] * {
        color: var(--text-primary) !important;
    }
    section[data-testid="stSidebar"] label {
        padding: 0.4rem 0.8rem !important;
        border-radius: 6px !important;
        margin: 2px 0 !important;
        transition: background 0.15s ease !important;
        color: var(--text-primary) !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] label:hover {
        background: var(--hover-overlay) !important;
    }
    section[data-testid="stSidebar"] label[data-selected="true"] {
        background: var(--accent-soft) !important;
        font-weight: 700 !important;
        color: var(--accent) !important;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 2px !important;
    }
    section[data-testid="stSidebar"] [data-testid="baseButton-secondary"] {
        color: var(--text-primary) !important;
        border: 1px solid var(--border) !important;
        background: transparent !important;
    }
    section[data-testid="stSidebar"] [data-testid="baseButton-secondary"]:hover {
        border-color: var(--accent) !important;
        background: var(--accent-soft) !important;
    }
    /* Buttons */
    .stButton button[kind="primary"] {
        background: var(--accent) !important;
        color: #FFFFFF !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.15) !important;
        font-weight: 600 !important;
        border: none !important;
    }
    .stButton button[kind="primary"]:hover {
        background: var(--accent-hover) !important;
        box-shadow: 0 4px 14px rgba(79,70,229,0.3) !important;
    }
    .stButton button[kind="secondary"] {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1.5px solid var(--border) !important;
        font-weight: 500 !important;
    }
    .stButton button[kind="secondary"]:hover {
        border-color: var(--accent) !important;
        background: var(--accent-soft) !important;
    }
    /* Text inputs */
    .stTextInput input {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1.5px solid var(--border) !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    }
    .stTextInput input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--focus-ring) !important;
    }
    .stTextInput input::placeholder {
        color: var(--text-secondary) !important;
        opacity: 0.7;
    }
    .stTextArea textarea {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1.5px solid var(--border) !important;
    }
    .stTextArea textarea:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--focus-ring) !important;
    }
    /* File uploader */
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
    /* Select / dropdown */
    div[data-baseweb="select"] > div {
        background: var(--bg-secondary) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="select"] * {
        color: var(--text-primary) !important;
    }
    div[data-baseweb="popover"] {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
    }
    /* Slider */
    div[data-testid="stSlider"] label {
        color: var(--text-primary) !important;
    }
    /* Metrics / KPIs */
    div[data-testid="metric-container"] {
        background: var(--bg-secondary) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    }
    div[data-testid="metric-container"] label {
        color: var(--text-secondary) !important;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
    }
    /* DataFrames / tables */
    .stDataFrame {
        border-radius: 10px !important;
        overflow: hidden !important;
        border: 1.5px solid var(--border) !important;
    }
    .stDataFrame [data-testid="StyledDataFrameColHeader"] {
        background: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    .stDataFrame [data-testid="StyledDataFrameRowHeader"] {
        color: var(--text-primary) !important;
    }
    /* All markdown text (the main content) */
    .stMarkdown, .stMarkdown * {
        color: var(--text-primary) !important;
    }
    .stMarkdown p, .stMarkdown li, .stMarkdown h1, .stMarkdown h2,
    .stMarkdown h3, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
        color: var(--text-primary) !important;
    }
    .stMarkdown code {
        color: var(--text-primary) !important;
        background: var(--bg-tertiary) !important;
    }
    .stCaption, .st-emotion-caption {
        color: var(--text-secondary) !important;
    }
    /* Tabs */
    button[data-baseweb="tab"] {
        color: var(--text-primary) !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--accent) !important;
        font-weight: 600 !important;
    }
    /* Dividers */
    hr {
        border-color: var(--border) !important;
        opacity: 1 !important;
    }
    /* Toast / notification */
    div[data-testid="stToast"] {
        background: var(--bg-secondary) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 10px !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.18) !important;
    }
    div[data-testid="stToast"] * {
        color: var(--text-primary) !important;
    }
    /* Expander */
    .streamlit-expanderHeader {
        color: var(--text-primary) !important;
        background: var(--bg-primary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }
    .streamlit-expanderHeader:hover {
        background: var(--hover-overlay) !important;
    }
    /* Spinner */
    .stSpinner {
        text-align: center;
        padding: 2rem 0;
        color: var(--text-secondary) !important;
    }
    /* Chat messages */
    .rag-chat-user {
        background: var(--accent) !important;
        color: #FFFFFF !important;
    }
    .rag-chat-assistant {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
    }
    .rag-chat-assistant * {
        color: var(--text-primary) !important;
    }
    /* General text catch-all for unthemed elements */
    .stApp {
        color: var(--text-primary) !important;
    }
    .stApp p, .stApp span, .stApp div, .stApp label, .stApp li {
        color: var(--text-primary) !important;
    }
    /* Checkbox / radio */
    label[data-testid="stWidgetLabel"] {
        color: var(--text-primary) !important;
    }
    div[role="checkbox"] {
        color: var(--text-primary) !important;
    }
    .stCheckbox label {
        color: var(--text-primary) !important;
    }
    /* Number input */
    .stNumberInput input {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1.5px solid var(--border) !important;
    }
    /* Info/warning/error/success boxes */
    div[data-testid="stAlert"] {
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }
    div[data-testid="stAlert"] * {
        color: var(--text-primary) !important;
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
    label = "☀️ Light" if current == "dark" else "🌙 Dark"
    if st.button(label, key="theme_toggle_btn"):
        st.session_state.theme = "light" if current == "dark" else "dark"
        st.rerun()
