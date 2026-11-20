"""Fixtures shared across the suite."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from first_light.app import app
from first_light.web import rate_limit


@pytest.fixture
def client() -> TestClient:
    """A client for the whole app, middleware included."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def fresh_rate_limit() -> Iterator[None]:
    """Starts and ends every test with no caller on the rate limit."""
    rate_limit._last_request.clear()
    yield
    rate_limit._last_request.clear()
