"""Tests for the login/register page.

Verifies the login page renders when unauthenticated and
redirects away when authenticated.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


class TestLoginPage:
    """Login page shows for unauthenticated users."""

    def test_login_page_shows_when_unauthenticated(self) -> None:
        """App shows login/register tabs when no auth_token."""
        at = AppTest.from_file("app.py")
        at.run()

        # Should have tabs for Sign In / Register
        tabs = at.tabs
        assert len(tabs) >= 1, "Expected login/register tabs"
        tab_texts = " ".join(t.label for t in tabs)
        assert "Sign In" in tab_texts or "Register" in tab_texts, (
            f"No login/register tabs found. Got: {tab_texts}"
        )

    def test_login_page_has_form(self) -> None:
        """Login page has email and password fields."""
        at = AppTest.from_file("app.py")
        at.run()

        text_inputs = at.text_input
        # login_email, login_password, reg_email, reg_password, reg_name
        assert len(text_inputs) >= 2, (
            f"Expected at least 2 text inputs on login page, got {len(text_inputs)}"
        )

    def test_authenticated_user_does_not_see_login(self) -> None:
        """Sidebar nav is shown instead of login when auth_token is set."""
        at = AppTest.from_file("app.py")
        at.session_state["auth_token"] = "test-token"
        at.run()

        # Should NOT have login tabs
        tabs = at.tabs
        login_tabs = [t for t in tabs if "Sign In" in t.label or "Register" in t.label]
        assert len(login_tabs) == 0, (
            "Login tabs shown despite auth_token being set"
        )

        # Should have sidebar radio nav instead
        radios = at.sidebar.radio
        nav_radios = [r for r in radios if r.key == "nav_radio"]
        assert len(nav_radios) == 1, "Expected sidebar nav for authenticated user"
