"""Playwright E2E test configuration.

Launches Chrome (headless) against the running RAG-CRM frontend
at http://localhost:8501.
"""

from __future__ import annotations

from typing import Generator

import pytest
from playwright.sync_api import Page, Playwright, expect


@pytest.fixture(scope="session")
def browser(playwright: Playwright) -> Generator:
    """Launch Chromium browser once per session."""
    browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture(scope="function")
def page(browser) -> Generator:  # type: ignore[no-untyped-def]  # noqa: ANN001
    """Open a new browser page for each test."""
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        device_scale_factor=1,
    )
    p = ctx.new_page()
    yield p
    ctx.close()


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL of the running Streamlit frontend."""
    return "http://localhost:8501"
