"""Shared fixtures for Streamlit AppTest frontend tests.

Uses st.testing.v1.AppTest to run the Streamlit app in a
headless subprocess for component-level testing.
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(scope="function")
def app() -> Generator[AppTest, None, None]:
    """Load the Streamlit app and run it via AppTest.

    Mocks out httpx client calls so the app doesn't need
    a live backend during unit tests.
    """
    at = AppTest.from_file("app.py")
    # Mock the full httpx module so page rendering doesn't fail
    with patch("httpx.Client") as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.get.return_value.raise_for_status.return_value = None
        mock_instance.get.return_value.json.return_value = {}

        at.run()
        yield at


@pytest.fixture(scope="function")
def app_no_mock() -> Generator[AppTest, None, None]:
    """Load app WITHOUT mocking — catches import issues."""
    at = AppTest.from_file("app.py")
    at.run()
    yield at
