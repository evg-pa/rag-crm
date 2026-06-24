"""Tests for theme toggle component.

Verifies the theme toggle button label switches correctly
between dark and light modes.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


class TestThemeToggle:
    """Theme toggle toggles between dark and light states."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.at = AppTest.from_file("app.py")
        self.at.run()

    def test_theme_defaults_to_dark(self) -> None:
        """Initial theme is 'dark'."""
        assert self.at.session_state["theme"] == "dark"

    def test_dark_mode_button_label(self) -> None:
        """When theme=dark, button shows '🌙 Dark'."""
        buttons = self.at.sidebar.button
        theme_btn = [b for b in buttons if b.key == "theme_toggle_btn"]
        assert len(theme_btn) >= 1
        # In dark mode, the label is "🌙 Dark"
        assert "🌙" in theme_btn[0].label

    def test_toggle_switches_to_light(self) -> None:
        """Clicking the toggle switches theme to 'light'."""
        buttons = self.at.sidebar.button
        theme_btn = [b for b in buttons if b.key == "theme_toggle_btn"]
        assert len(theme_btn) >= 1

        # Click the toggle button
        theme_btn[0].click()
        self.at.run()

        assert self.at.session_state["theme"] == "light"

    def test_light_mode_button_label(self) -> None:
        """After switching to light, button shows '☀️ Light'."""
        buttons = self.at.sidebar.button
        theme_btn = [b for b in buttons if b.key == "theme_toggle_btn"]
        assert len(theme_btn) >= 1

        # Click to switch to light
        theme_btn[0].click()
        self.at.run()

        buttons2 = self.at.sidebar.button
        theme_btn2 = [b for b in buttons2 if b.key == "theme_toggle_btn"]
        assert len(theme_btn2) >= 1
        assert "☀️" in theme_btn2[0].label, (
            f"Expected '☀️' in button label, got '{theme_btn2[0].label}'"
        )
