"""Tests for CORS on error paths, 500 logging, and 422 shape."""

import logging

import pytest
from fastapi.testclient import TestClient

from src.app import app

_BIG = "/v1/big-endian-first-light"
_ORIGIN = {"Origin": "http://example.com"}
_PAYLOAD = {"birthday": "2000-06-15", "as_of": "2025-06-15"}


@pytest.fixture(scope="module")
def error_client():
    """Client with a temporary crashing route and 500s enabled.

    ``raise_server_exceptions=False`` lets the app's own 500
    handler produce the response instead of re-raising into
    the test.
    """
    async def boom() -> None:
        raise RuntimeError("boom")

    route_count = len(app.router.routes)
    app.add_api_route("/_test/boom", boom, methods=["GET"])
    yield TestClient(app, raise_server_exceptions=False)
    del app.router.routes[route_count:]


class TestCorsOnErrorPaths:
    """Cross-origin browsers must be able to read every error."""

    def test_cors_header_on_success(self, client):
        resp = client.post(
            _BIG, json=_PAYLOAD, headers=_ORIGIN,
        )
        assert resp.status_code == 200
        assert (
            resp.headers["access-control-allow-origin"] == "*"
        )

    def test_cors_header_on_429(self, client):
        first = client.post(
            _BIG, json=_PAYLOAD, headers=_ORIGIN,
        )
        assert first.status_code == 200

        limited = client.post(
            _BIG, json=_PAYLOAD, headers=_ORIGIN,
        )
        assert limited.status_code == 429
        assert (
            limited.headers["access-control-allow-origin"]
            == "*"
        )
        assert "Retry-After" in limited.headers

    def test_cors_header_on_422(self, client):
        resp = client.post(
            _BIG, json={"birthday": "bad"}, headers=_ORIGIN,
        )
        assert resp.status_code == 422
        assert (
            resp.headers["access-control-allow-origin"] == "*"
        )

    def test_cors_header_on_500(self, error_client):
        resp = error_client.get("/_test/boom", headers=_ORIGIN)
        assert resp.status_code == 500
        assert resp.json() == {
            "detail": "An unexpected error occurred.",
        }
        assert (
            resp.headers["access-control-allow-origin"] == "*"
        )

    def test_no_cors_header_without_origin(self, error_client):
        resp = error_client.get("/_test/boom")
        assert resp.status_code == 500
        assert "access-control-allow-origin" not in resp.headers


class TestErrorLogging:
    """Requests that end in a 500 still hit the access log."""

    def test_500_request_is_logged(self, error_client, caplog):
        with caplog.at_level(logging.INFO, logger="src.app"):
            resp = error_client.get("/_test/boom")
        assert resp.status_code == 500
        access_lines = [
            r.getMessage() for r in caplog.records
            if "/_test/boom" in r.getMessage()
            and "GET" in r.getMessage()
        ]
        assert access_lines, "500 request missing from access log"
        assert "500" in access_lines[0]


class TestValidation422Shape:
    """Every 422 body carries ``detail`` as a plain string."""

    @pytest.mark.parametrize("payload", [
        {"birthday": "not-a-date"},               # parser error
        {"birthday": "2099-01-01"},               # future date
        {},                                       # missing field
        {"birthday": "2000-06-15",
         "star_limit": 0},                        # bounds error
        {"birthday": "2000-06-15",
         "categories": ["nope"]},                 # unknown category
        {"birthday": "2000-06-15",
         "categories": []},                       # empty list
        {"birthday": 20000615},                   # wrong type
    ])
    def test_detail_is_string(self, client, payload):
        resp = client.post(_BIG, json=payload)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, str)
        assert detail
