"""E2E tests for theme toggle functionality."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


class TestThemeToggle:
    """Dark/Light theme toggle works in the browser."""

    def test_theme_toggle_button_visible(self, page: Page, base_url: str) -> None:
        """Theme toggle button renders in the sidebar."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        sidebar = page.locator("section[data-testid='stSidebar']")
        toggle = sidebar.get_by_role("button").filter(has_text="🌙")
        expect(toggle).to_be_visible()

    def test_toggle_switches_to_light(self, page: Page, base_url: str) -> None:
        """Clicking the toggle changes the button label from 🌙 to ☀️."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        sidebar = page.locator("section[data-testid='stSidebar']")
        # Find and click the toggle
        toggle = sidebar.get_by_role("button").filter(has_text="🌙")
        expect(toggle).to_be_visible()
        toggle.click()
        page.wait_for_timeout(1500)  # Wait for rerun

        # Now the button should show the light mode label
        light_toggle = sidebar.get_by_role("button").filter(has_text="☀️")
        expect(light_toggle).to_be_visible()

    def test_toggle_roundtrip(self, page: Page, base_url: str) -> None:
        """Toggle: dark → light → dark works."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

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
