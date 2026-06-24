"""Tests for the sidebar navigation component.

Uses AppTest to verify the sidebar renders with all expected
elements: navigation options, theme toggle, settings slider,
and version info.
"""

from __future__ import annotations

import pytest


class TestSidebarRendering:
    """The sidebar should render all navigation and control elements."""

    @pytest.fixture(autouse=True)
    def _setup(self, app) -> None:  # noqa: ANN001
        self.at = app

    def test_sidebar_has_title(self) -> None:
        """Sidebar displays the RAG-CRM heading."""
        sidebar_md = self.at.sidebar.markdown
        titles = [m for m in sidebar_md if "RAG-CRM" in m.value]
        assert len(titles) >= 1, "RAG-CRM heading not found in sidebar"

    def test_six_nav_options(self) -> None:
        """Sidebar radio has exactly 6 navigation options."""
        radio = self.at.sidebar.radio
        nav_radios = [r for r in radio if r.key == "nav_radio"]
        assert len(nav_radios) == 1, "Expected exactly one nav_radio widget"
        expected_options = [
            "📊 Dashboard",
            "📄 Documents",
            "💬 Q&A Chat",
            "🔍 Search",
            "📚 Knowledge Base",
            "⚙️ Pipeline",
        ]
        assert nav_radios[0].options == expected_options, (
            f"Nav options mismatch.\n"
            f"  Expected: {expected_options}\n"
            f"  Got:      {nav_radios[0].options}"
        )

    def test_no_duplicate_nav(self) -> None:
        """Only ONE navigation radio widget exists (no auto-nav duplication)."""
        radio = self.at.sidebar.radio
        nav_radios = [r for r in radio if "nav" in (r.key or "").lower()]
        assert len(nav_radios) == 1, (
            f"Expected 1 nav radio, found {len(nav_radios)}. "
            "If 2 exist, Streamlit's auto-generated pages/ nav is still active."
        )

    def test_theme_toggle_button_exists(self) -> None:
        """Sidebar has a theme toggle button."""
        buttons = self.at.sidebar.button
        theme_btn = [b for b in buttons if b.key == "theme_toggle_btn"]
        assert len(theme_btn) >= 1, "Theme toggle button not found"

    def test_top_k_slider_exists(self) -> None:
        """Sidebar has the Search Top-K slider."""
        sliders = self.at.sidebar.slider
        top_k = [s for s in sliders if s.key == "top_k_slider"]
        assert len(top_k) >= 1, "Top-K slider not found (key='top_k_slider')"
        # AppTest slider API — check the value is within expected range
        val = int(top_k[0].value)  # type: ignore[arg-type]  # noqa: PGH003
        assert 1 <= val <= 50, (
            f"Expected slider value between 1 and 50, got {val}"
        )

    def test_version_displayed(self) -> None:
        """Session state has app_version set."""
        assert self.at.session_state["app_version"] == "0.1.0"

    def test_no_auth_button_in_sidebar(self) -> None:
        """Sidebar has no Sign In button (auth removed)."""
        buttons = self.at.sidebar.button
        auth_btns = [b for b in buttons if b.key == "login_nav_btn" or "Sign In" in str(b)]
        assert len(auth_btns) == 0, (
            "Sign In button found in sidebar — auth should be fully removed"
        )

    def test_no_user_info_in_sidebar(self) -> None:
        """Sidebar has no user info section (auth removed)."""
        sidebar_md = self.at.sidebar.markdown
        user_refs = [m for m in sidebar_md if "👤" in m.value]
        assert len(user_refs) == 0, (
            "User emoji found in sidebar — auth should be fully removed"
        )
