"""Playwright E2E test configuration.

Launches Chrome (headless) against the running RAG-CRM frontend
at http://localhost:8501. The default ``page`` fixture auto-logs
in with test credentials before every test.
"""

from __future__ import annotations

from typing import Generator

import pytest
from playwright.sync_api import Page, Playwright, expect


# Test credentials — must match a registered user in the backend
TEST_EMAIL = "test@ragcrm.demo"
TEST_PASSWORD="testpass1234"


@pytest.fixture(scope="session")
def browser(playwright: Playwright) -> Generator:
    """Launch Chromium browser once per session."""
    browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()


def _do_login(page: Page, base_url: str) -> None:
    """Navigate to the app and sign in with test credentials."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    # Fill email (input[type=text]) and password fields
    page.locator('input[type="text"]').first.fill(TEST_EMAIL)
    page.locator('input[type="password"]').first.fill(TEST_PASSWORD)

    # Click the form submit button in the Sign In tab
    page.locator('button[kind="primaryFormSubmit"]').first.click()

    # Wait for auth to complete and dashboard to render
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")


@pytest.fixture(scope="function")
def page(browser, base_url: str) -> Generator:  # type: ignore[no-untyped-def]  # noqa: ANN001
    """Open a browser page and log in.

    Yields an authenticated page ready for navigation tests.
    """
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        device_scale_factor=1,
    )
    p = ctx.new_page()
    _do_login(p, base_url)
    yield p
    ctx.close()


@pytest.fixture(scope="function")
def public_page(browser, base_url: str) -> Generator:  # type: ignore[no-untyped-def]  # noqa: ANN001
    """Open a browser page WITHOUT logging in (for login page tests)."""
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        device_scale_factor=1,
    )
    p = ctx.new_page()
    p.goto(base_url)
    p.wait_for_load_state("networkidle")
    yield p
    ctx.close()


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL of the running Streamlit frontend."""
    return "http://localhost:8501"
