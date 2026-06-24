"""Page: Login / Register — authenticate with the RAG-CRM backend."""

from __future__ import annotations

import streamlit as st

from utils import api, state


def _handle_login(email: str, password: str) -> None:
    """Authenticate and store token in session state."""
    try:
        result = api.login(email, password)
        st.session_state.auth_token = result["access_token"]
        st.session_state.current_page = "dashboard"
        # Fetch user profile
        try:
            st.session_state.auth_user = api.get_me()
        except Exception:
            st.session_state.auth_user = {"email": email}
        state.invalidate_caches()
        st.rerun()
    except Exception as exc:
        st.error(f"❌ Login failed: {exc}")


def _handle_register(email: str, password: str, display_name: str) -> None:
    """Create account and store token in session state."""
    try:
        result = api.register(email, password, display_name)
        st.session_state.auth_token = result["access_token"]
        st.session_state.current_page = "dashboard"
        st.session_state.auth_user = {
            "email": email,
            "display_name": display_name or email.split("@")[0],
        }
        state.invalidate_caches()
        st.rerun()
    except Exception as exc:
        st.error(f"❌ Registration failed: {exc}")


def render() -> None:
    """Render the login / register page."""
    # Centre the form on the page
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            "<h1 style='text-align:center;'>📄 RAG-CRM</h1>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center;color:var(--text-secondary);'>"
            "Sign in to access the document management system</p>",
            unsafe_allow_html=True,
        )
        st.divider()

        tab_login, tab_register = st.tabs(["🔑 Sign In", "📝 Register"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input(
                    "Email",
                    placeholder="you@example.com",
                    key="login_email",
                )
                password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="Enter your password",
                    key="login_password",
                )
                submitted = st.form_submit_button(
                    "🔑 Sign In",
                    type="primary",
                    use_container_width=True,
                )
                if submitted:
                    _handle_login(email, password)

        with tab_register:
            with st.form("register_form"):
                reg_email = st.text_input(
                    "Email",
                    placeholder="you@example.com",
                    key="reg_email",
                )
                reg_password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="At least 8 characters",
                    key="reg_password",
                )
                reg_name = st.text_input(
                    "Display Name (optional)",
                    placeholder="Your name",
                    key="reg_name",
                )
                reg_submitted = st.form_submit_button(
                    "📝 Create Account",
                    type="primary",
                    use_container_width=True,
                )
                if reg_submitted:
                    _handle_register(reg_email, reg_password, reg_name)
