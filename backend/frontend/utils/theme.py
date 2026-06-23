"""Theme management — dark/light toggle and CSS injection."""

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


def _dark_css() -> str:
    """CSS overrides for dark theme."""
    return """
    <style>
    /* Dark theme overrides */
    :root {
        --bg-primary: #0E1117;
        --bg-secondary: #1A1C23;
        --bg-tertiary: #262730;
        --text-primary: #E0E0E0;
        --text-secondary: #9E9EB0;
        --accent: #7C73FF;
        --accent-hover: #6D63F0;
        --success: #34D399;
        --warning: #FBBF24;
        --error: #F87171;
        --border: #333540;
    }
    .stApp { background-color: var(--bg-primary); }
    section[data-testid="stSidebar"] { background-color: var(--bg-secondary); }
    </style>
    """


def _light_css() -> str:
    """CSS overrides for light theme."""
    return """
    <style>
    /* Light theme overrides */
    :root {
        --bg-primary: #FFFFFF;
        --bg-secondary: #F5F5F5;
        --bg-tertiary: #EBEBEB;
        --text-primary: #1A1A2E;
        --text-secondary: #666680;
        --accent: #4F46E5;
        --accent-hover: #4338CA;
        --success: #10B981;
        --warning: #F59E0B;
        --error: #EF4444;
        --border: #E5E7EB;
    }
    .stApp { background-color: var(--bg-primary); }
    section[data-testid="stSidebar"] { background-color: var(--bg-secondary); }
    </style>
    """


def init_theme() -> None:
    """Initialize theme in session state and inject CSS."""
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    # Apply custom CSS
    load_css()

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
