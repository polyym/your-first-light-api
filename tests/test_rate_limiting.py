"""Tests for rate limiting, eviction, and proxy-aware IP extraction."""

import time

import pytest

import src.app as app_module
from src.app import RATE_LIMIT_SECONDS, _rate_limit

# Path -> a valid payload in that endpoint's date format.
_ENDPOINT_PAYLOADS = {
    "/v1/big-endian-first-light": {
        "birthday": "2000-06-15", "as_of": "2025-06-15",
    },
    "/v1/middle-endian-first-light": {
        "birthday": "06/15/2000", "as_of": "06/15/2025",
    },
    "/v1/little-endian-first-light": {
        "birthday": "15/06/2000", "as_of": "15/06/2025",
    },
}

_BIG = "/v1/big-endian-first-light"


class TestRateLimiting:
    """Verify per-IP rate limiting on POST endpoints."""

    @pytest.mark.parametrize("path", sorted(_ENDPOINT_PAYLOADS))
    def test_second_request_is_rate_limited(self, client, path):
        """Every rate-limited path enforces the limit itself."""
        payload = _ENDPOINT_PAYLOADS[path]
        resp1 = client.post(path, json=payload)
        assert resp1.status_code == 200

        resp2 = client.post(path, json=payload)
        assert resp2.status_code == 429
        assert "Rate limited" in resp2.json()["detail"]

    def test_limit_is_shared_across_endpoints(self, client):
        """One IP gets one slot across ALL rate-limited paths."""
        resp1 = client.post(
            _BIG, json=_ENDPOINT_PAYLOADS[_BIG],
        )
        assert resp1.status_code == 200

        other = "/v1/little-endian-first-light"
        resp2 = client.post(
            other, json=_ENDPOINT_PAYLOADS[other],
        )
        assert resp2.status_code == 429

    def test_health_not_rate_limited(self, client):
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_failed_request_releases_slot(self, client):
        """A 422 does not burn the caller's 30-second budget."""
        bad = client.post(_BIG, json={
            "birthday": "15/06/2000",
        })
        assert bad.status_code == 422

        good = client.post(_BIG, json=_ENDPOINT_PAYLOADS[_BIG])
        assert good.status_code == 200


class TestRateLimiterEviction:
    """Verify that stale rate-limit entries are evicted."""

    def test_stale_entries_are_evicted(self, client):
        _rate_limit["1.2.3.4"] = (
            time.time() - RATE_LIMIT_SECONDS - 10
        )
        _rate_limit["5.6.7.8"] = (
            time.time() - RATE_LIMIT_SECONDS - 5
        )
        assert len(_rate_limit) == 2

        resp = client.post(_BIG, json=_ENDPOINT_PAYLOADS[_BIG])
        assert resp.status_code == 200
        assert "1.2.3.4" not in _rate_limit
        assert "5.6.7.8" not in _rate_limit


class TestProxyIP:
    """Verify proxy-aware IP extraction for rate limiting."""

    def test_forwarded_header_ignored_by_default(self, client):
        """With no trusted proxies the header is spoofable junk.

        Varying X-Forwarded-For must not mint fresh rate-limit
        buckets when TRUSTED_PROXY_HOPS is 0 (the default).
        """
        payload = _ENDPOINT_PAYLOADS[_BIG]
        resp1 = client.post(
            _BIG, json=payload,
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp1.status_code == 200
        assert "10.0.0.1" not in _rate_limit

        resp2 = client.post(
            _BIG, json=payload,
            headers={"X-Forwarded-For": "10.0.0.2"},
        )
        assert resp2.status_code == 429

    def test_x_forwarded_for_used_behind_trusted_proxy(
        self, client, monkeypatch,
    ):
        """Behind one trusted proxy, the appended entry is used."""
        monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 1)
        payload = _ENDPOINT_PAYLOADS[_BIG]
        resp1 = client.post(
            _BIG, json=payload,
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp1.status_code == 200
        assert "10.0.0.1" in _rate_limit

        resp2 = client.post(
            _BIG, json=payload,
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp2.status_code == 429

        resp3 = client.post(
            _BIG, json=payload,
            headers={"X-Forwarded-For": "10.0.0.2"},
        )
        assert resp3.status_code == 200

    def test_client_prefix_is_never_trusted(
        self, client, monkeypatch,
    ):
        """Client-supplied entries left of the proxy's are ignored."""
        monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 1)
        payload = _ENDPOINT_PAYLOADS[_BIG]
        resp1 = client.post(
            _BIG, json=payload,
            headers={"X-Forwarded-For": "spoofed-1, 10.0.0.1"},
        )
        assert resp1.status_code == 200
        assert "10.0.0.1" in _rate_limit
        assert "spoofed-1" not in _rate_limit

        resp2 = client.post(
            _BIG, json=payload,
            headers={"X-Forwarded-For": "spoofed-2, 10.0.0.1"},
        )
        assert resp2.status_code == 429

    def test_two_hop_chain_selects_client_entry(
        self, client, monkeypatch,
    ):
        """With two trusted hops, the second-from-right is used."""
        monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 2)
        resp = client.post(
            _BIG, json=_ENDPOINT_PAYLOADS[_BIG],
            headers={
                "X-Forwarded-For": "203.0.113.5, 198.51.100.7",
            },
        )
        assert resp.status_code == 200
        assert "203.0.113.5" in _rate_limit
        assert "198.51.100.7" not in _rate_limit

    def test_short_chain_falls_back_to_leftmost(
        self, client, monkeypatch,
    ):
        """A chain shorter than the hop count uses the outermost."""
        monkeypatch.setattr(app_module, "TRUSTED_PROXY_HOPS", 3)
        resp = client.post(
            _BIG, json=_ENDPOINT_PAYLOADS[_BIG],
            headers={"X-Forwarded-For": "203.0.113.5"},
        )
        assert resp.status_code == 200
        assert "203.0.113.5" in _rate_limit
