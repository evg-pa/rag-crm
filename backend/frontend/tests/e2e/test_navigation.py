"""E2E tests for sidebar navigation.

Verifies the single unified navigation works correctly,
no duplicate nav exists, and all pages load without errors.

NOTE: The ``page`` fixture already logs in and is at the app root.
Do NOT call ``page.goto(base_url)`` — that would reset the auth.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


NAV_OPTIONS: list[tuple[str, str, str]] = [
    ("📊 Dashboard", "dashboard", "RAG-CRM"),
    ("📄 Documents", "documents", "Documents"),
    ("💬 Q&A Chat", "qa_chat", "Q&A"),
    ("🔍 Search", "search", "Search"),
    ("📚 Knowledge Base", "wiki", "Knowledge Base"),
    ("⚙️ Pipeline", "pipeline", "Pipeline"),
]


class TestNavigation:
    """All 6 nav options load correctly."""

    @pytest.mark.parametrize(
        ("nav_text", "expected_title"),
        [(n[0], n[2]) for n in NAV_OPTIONS],
        ids=[n[1] for n in NAV_OPTIONS],
    )
    def test_nav_loads_page(
        self,
        page: Page,
        nav_text: str,
        expected_title: str,
    ) -> None:
        """Clicking each nav option loads the correct page."""
        page.wait_for_load_state("networkidle")

        # Click the nav radio item by its label text
        radio_label = page.locator(f"label:has-text('{nav_text}')")
        expect(radio_label).to_be_visible()
        radio_label.click()
        page.wait_for_timeout(1000)  # Let Streamlit re-render

        # Verify page content loaded
        body = page.locator("body")
        expect(body).to_contain_text(expected_title)

    def test_no_duplicate_sidebar_nav(self, page: Page) -> None:
        """Only ONE radiogroup with 6 nav items exists (no auto-nav)."""
        page.wait_for_load_state("networkidle")

        radios = page.locator(
            "section[data-testid='stSidebar'] div[role='radiogroup']"
        )
        radio_count = radios.count()
        assert radio_count == 1, (
            f"Expected 1 radiogroup in sidebar, found {radio_count}. "
            "If >1, auto-generated pages/ nav is still active."
        )

        # Verify the single radiogroup has exactly 6 options
        options = radios.locator("label")
        option_count = options.count()
        assert option_count == 6, (
            f"Expected 6 nav options, found {option_count}. "
            "If >6, auto-generated pages/ nav might be duplicating."
        )

    def test_sidebar_title(self, page: Page) -> None:
        """Sidebar shows RAG-CRM heading."""
        page.wait_for_load_state("networkidle")
        sidebar = page.locator("section[data-testid='stSidebar']")
        expect(sidebar).to_contain_text("RAG-CRM")

    def test_version_in_sidebar(self, page: Page) -> None:
        """Sidebar footer shows version."""
        sidebar = page.locator("section[data-testid='stSidebar']")
        expect(sidebar).to_contain_text("v0.1.0")

    def test_top_k_slider_exists(self, page: Page) -> None:
        """Search Top-K slider is present in sidebar."""
        slider = page.locator("section[data-testid='stSidebar']").locator(
            "div[data-testid='stSlider']"
        )
        expect(slider).to_be_visible()
