"""Tests for the access log line written for every request."""

import logging

import pytest
from fastapi.testclient import TestClient

from first_light.app import app
from first_light.web import access_log, client_ip, routes

BIG = "/v1/big-endian-first-light"
REQUEST = {
    "birthday": "1998-11-15",
    "as_of": "2026-11-18",
    "categories": ["links"],
}


class SteppingClock:
    """A monotonic clock that moves 37.6 ms each time it is read."""

    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        self.now += 0.0376
        return self.now


@pytest.fixture
def lines(monkeypatch, caplog):
    """Gives the access log lines written so far."""
    monkeypatch.setattr(access_log, "time", SteppingClock())
    caplog.set_level(logging.INFO, logger=access_log.logger.name)

    def written():
        return [
            record.getMessage()
            for record in caplog.records
            if record.name == access_log.logger.name
        ]

    return written


def test_app_lets_the_access_log_through():
    """The image runs uvicorn with its own access log switched off."""
    assert access_log.logger.isEnabledFor(logging.INFO)


def test_line_gives_method_path_status_rounded_duration_and_caller(
    client, lines
):
    client.get("/health")
    assert lines() == ["GET /health 200 38ms testclient"]


def test_line_leaves_out_the_query_string(client, lines):
    client.get("/health?probe=1")
    assert lines() == ["GET /health 200 38ms testclient"]


def test_host_header_that_is_no_address_is_answered_and_logged(client, lines):
    """The scope's path is logged, whatever the Host header holds."""
    response = client.get("/health", headers={"Host": "[:0]"})

    assert response.status_code == 200
    assert lines() == ["GET /health 200 38ms testclient"]


def test_line_names_the_caller_the_platform_header_gives(
    client, lines, monkeypatch
):
    monkeypatch.setattr(client_ip, "CLIENT_IP_HEADER", "True-Client-IP")
    client.get("/health", headers={"True-Client-IP": "203.0.113.5"})
    assert lines() == ["GET /health 200 38ms 203.0.113.5"]


@pytest.mark.parametrize(
    "path",
    [
        "/health%0AGET%20/forged",
        "/health%20200%201ms%20198.51.100.7%1B%5B2J%0A",
    ],
    ids=["second-line", "fields-and-escape"],
)
def test_path_that_could_forge_a_line_is_percent_encoded(client, lines, path):
    """The server decodes a path, so the app sees its spaces and escapes."""
    client.get(path)
    assert lines() == [f"GET {path} 404 38ms testclient"]


@pytest.mark.parametrize(
    ("sent", "logged"),
    [
        ("2001:db8::5", "2001:db8::5"),
        ("203.0.113.5 GET /health 200", "203.0.113.5%20GET%20/health%20200"),
    ],
    ids=["ipv6-as-it-is", "spaces-encoded"],
)
def test_caller_from_a_header_is_percent_encoded(
    client, lines, monkeypatch, sent, logged
):
    monkeypatch.setattr(client_ip, "CLIENT_IP_HEADER", "True-Client-IP")
    client.get("/health", headers={"True-Client-IP": sent})
    assert lines() == [f"GET /health 200 38ms {logged}"]


def test_preflight_answered_by_cors_is_logged(client, lines):
    client.options(
        BIG,
        headers={
            "Origin": "https://example.org",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert lines() == [f"OPTIONS {BIG} 200 38ms testclient"]


def test_429_answered_by_the_rate_limiter_is_logged(client, lines):
    client.post(BIG, json=REQUEST)
    client.post(BIG, json=REQUEST)
    assert lines() == [
        f"POST {BIG} 200 38ms testclient",
        f"POST {BIG} 429 38ms testclient",
    ]


def test_request_that_raises_is_logged_as_a_500(lines, monkeypatch):
    def broken(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "compute_first_light", broken)
    TestClient(app, raise_server_exceptions=False).post(BIG, json=REQUEST)
    assert lines() == [f"POST {BIG} 500 38ms testclient"]
