"""Shared fixtures for the Your First Light test suite."""

import pytest
from fastapi.testclient import TestClient

from src.app import _rate_limit, app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Module-scoped test client — created once per test file.

    Returns:
        A ``TestClient`` wrapping the FastAPI application.
    """
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_rate_limit() -> None:
    """Clear the in-memory rate limiter before every test.

    Runs automatically (``autouse=True``) to ensure test
    isolation for rate-limiting state.
    """
    _rate_limit.clear()
