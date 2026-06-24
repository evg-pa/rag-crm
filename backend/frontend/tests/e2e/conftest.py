"""Playwright E2E test configuration.

Launches Chrome (headless) against the running RAG-CRM frontend
at http://localhost:8501. No auth is needed — the app is fully open.
"""

from __future__ import annotations

from typing import Generator

import pytest
from playwright.sync_api import Playwright


@pytest.fixture(scope="session")
def browser(playwright: Playwright) -> Generator:
    """Launch Chromium browser once per session."""
    browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture(scope="function")
def page(browser, base_url: str) -> Generator:  # type: ignore[no-untyped-def]  # noqa: ANN001
    """Open a browser page at the app root (no auth needed)."""
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
