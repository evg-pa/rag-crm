"""E2E tests for theme toggle functionality.

NOTE: The ``page`` fixture already logs in.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


class TestThemeToggle:
    """Dark/Light theme toggle works in the browser."""

    def test_theme_toggle_button_visible(self, page: Page) -> None:
        """Theme toggle button renders in the sidebar."""
        sidebar = page.locator("section[data-testid='stSidebar']")
        toggle = sidebar.get_by_role("button").filter(has_text="🌙")
        expect(toggle).to_be_visible()

    def test_toggle_switches_to_light(self, page: Page) -> None:
        """Clicking the toggle changes the button label from 🌙 to ☀️."""
        sidebar = page.locator("section[data-testid='stSidebar']")
        toggle = sidebar.get_by_role("button").filter(has_text="🌙")
        expect(toggle).to_be_visible()
        toggle.click()
        page.wait_for_timeout(1500)

        light_toggle = sidebar.get_by_role("button").filter(has_text="☀️")
        expect(light_toggle).to_be_visible()

    def test_toggle_roundtrip(self, page: Page) -> None:
        """Toggle: dark → light → dark works."""
        sidebar = page.locator("section[data-testid='stSidebar']")

        # Dark → Light
        dark_btn = sidebar.get_by_role("button").filter(has_text="🌙")
        dark_btn.click()
        page.wait_for_timeout(1500)

        light_btn = sidebar.get_by_role("button").filter(has_text="☀️")
        expect(light_btn).to_be_visible()

        # Light → Dark
        light_btn.click()
        page.wait_for_timeout(1500)

        dark_btn2 = sidebar.get_by_role("button").filter(has_text="🌙")
        expect(dark_btn2).to_be_visible()
