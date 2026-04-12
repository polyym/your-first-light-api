"""Tests for rate limiting, eviction, and proxy-aware IP extraction."""

import time

from src.app import RATE_LIMIT_SECONDS, _rate_limit


class TestRateLimiting:
    """Verify per-IP rate limiting on POST endpoints."""

    def test_second_request_is_rate_limited(self, client):
        payload = {
            "birthday": "2000-06-15", "as_of": "2025-06-15",
        }
        resp1 = client.post(
            "/v1/big-endian-first-light", json=payload,
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            "/v1/big-endian-first-light", json=payload,
        )
        assert resp2.status_code == 429
        assert "Rate limited" in resp2.json()["detail"]

    def test_health_not_rate_limited(self, client):
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200


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

        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15", "as_of": "2025-06-15",
        })
        assert resp.status_code == 200
        assert "1.2.3.4" not in _rate_limit
        assert "5.6.7.8" not in _rate_limit


class TestProxyIP:
    """Verify proxy-aware IP extraction for rate limiting."""

    def test_x_forwarded_for_is_used(self, client):
        """Rate limiter keys on the X-Forwarded-For IP."""
        payload = {
            "birthday": "2000-06-15", "as_of": "2025-06-15",
        }
        resp1 = client.post(
            "/v1/big-endian-first-light",
            json=payload,
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp1.status_code == 200
        assert "10.0.0.1" in _rate_limit

        resp2 = client.post(
            "/v1/big-endian-first-light",
            json=payload,
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp2.status_code == 429

        resp3 = client.post(
            "/v1/big-endian-first-light",
            json=payload,
            headers={"X-Forwarded-For": "10.0.0.2"},
        )
        assert resp3.status_code == 200

    def test_x_forwarded_for_multi_hop(self, client):
        """Rightmost IP (proxy-added, not spoofable) is used."""
        payload = {
            "birthday": "2000-06-15", "as_of": "2025-06-15",
        }
        resp = client.post(
            "/v1/big-endian-first-light",
            json=payload,
            headers={
                "X-Forwarded-For": "203.0.113.5, 10.0.0.1",
            },
        )
        assert resp.status_code == 200
        assert "10.0.0.1" in _rate_limit
