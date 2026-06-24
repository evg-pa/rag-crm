"""Tests for the login/register page.

Auth is optional — the login page is a regular navigable page,
not a forced redirect.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


class TestLoginPage:
    """Login page shows when navigated to."""

    def test_login_page_shows_when_navigated_to(self) -> None:
        """App shows login/register tabs when current_page='login'."""
        at = AppTest.from_file("app.py")
        at.session_state["current_page"] = "login"
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
        at.session_state["current_page"] = "login"
        at.run()

        text_inputs = at.text_input
        # login_email, login_password, reg_email, reg_password, reg_name
        assert len(text_inputs) >= 2, (
            f"Expected at least 2 text inputs on login page, got {len(text_inputs)}"
        )

    def test_authenticated_user_can_visit_login_page(self) -> None:
        """Login page still renders even if user is authenticated."""
        at = AppTest.from_file("app.py")
        at.session_state["auth_token"] = "test-token"
        at.session_state["current_page"] = "login"
        at.run()

        # Login tabs should still be visible
        tabs = at.tabs
        tab_texts = " ".join(t.label for t in tabs)
        assert "Sign In" in tab_texts or "Register" in tab_texts, (
            "Login tabs should show even when auth_token is set (login is a page)"
        )

    def test_default_page_is_dashboard_not_login(self) -> None:
        """With no auth_token, app defaults to dashboard page (not forced to login)."""
        at = AppTest.from_file("app.py")
        at.run()

        # Should NOT have login tabs by default
        tabs = at.tabs
        login_tabs = [t for t in tabs if "Sign In" in t.label or "Register" in t.label]
        assert len(login_tabs) == 0, (
            "Login tabs should NOT appear by default (auth is optional)"
        )

    def test_authenticated_user_does_not_see_login(self) -> None:
        """Authenticated user on dashboard does not see login tabs."""
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
