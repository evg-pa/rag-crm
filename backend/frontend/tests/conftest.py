"""Shared fixtures for Streamlit AppTest frontend tests.

Uses st.testing.v1.AppTest to run the Streamlit app in a
headless subprocess for component-level testing.

Sets a test auth token by default so the app renders the
authenticated sidebar + pages (not the login page).
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope="function")
def app() -> Generator[AppTest, None, None]:
    """Load the Streamlit app with a test auth token.

    Sets auth_token before AppTest.run() so the app skips the
    login page and renders the authenticated sidebar + routing.
    """
    at = AppTest.from_file("app.py")
    # Pre-set auth token so the app authenticates on startup
    at.session_state["auth_token"] = "test-token-for-apptest"
    at.run()
    yield at


@pytest.fixture(scope="function")
def app_authenticated() -> Generator[AppTest, None, None]:
    """Load app with auth token and mocked API — for page tests."""
    at = AppTest.from_file("app.py")
    at.session_state["auth_token"] = "test-token"
    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.get.return_value.raise_for_status.return_value = None
        mock_instance.get.return_value.json.return_value = {}
        at.run()
        yield at
