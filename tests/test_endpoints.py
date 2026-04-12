"""Tests for API endpoints, validation, and edge cases."""

from datetime import date, timedelta

import pytest


class TestHealth:
    """Verify the ``/health`` readiness probe."""

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["stars_loaded"] > 0
        assert data["eclipses_loaded"] > 0


class TestBigEndian:
    """Tests for the ``/v1/big-endian-first-light`` endpoint."""

    def test_valid_request(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["birthday"] == "2000-06-15"
        assert data["as_of"] == "2025-06-15"
        assert "age_years" in data
        assert data["age_years"] == pytest.approx(25.0, abs=0.1)

    def test_category_filtering(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["time_alive"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "age_years" in data
        assert "stars" not in data
        assert "body_stats" not in data
        assert "cosmic_journey" not in data
        assert "moon_phase_at_midnight_utc" not in data

    def test_links_only(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["links"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "nasa_apod_url" in data
        assert "age_years" not in data


class TestMiddleEndian:
    """Tests for the ``/v1/middle-endian-first-light`` endpoint."""

    def test_valid_request(self, client):
        resp = client.post("/v1/middle-endian-first-light", json={
            "birthday": "06/15/2000",
            "as_of": "06/15/2025",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["birthday"] == "2000-06-15"


class TestLittleEndian:
    """Tests for the ``/v1/little-endian-first-light`` endpoint."""

    def test_valid_request(self, client):
        resp = client.post("/v1/little-endian-first-light", json={
            "birthday": "15/06/2000",
            "as_of": "15/06/2025",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["birthday"] == "2000-06-15"


class TestValidation:
    """Verify request validation and error responses."""

    def test_invalid_date_format(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "not-a-date",
        })
        assert resp.status_code == 422

    def test_future_birthday(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2099-01-01",
        })
        assert resp.status_code == 422

    def test_birthday_equals_as_of(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2000-06-15",
        })
        assert resp.status_code == 422

    def test_invalid_as_of(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "bad-date",
        })
        assert resp.status_code == 422

    def test_birthday_string_too_long(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01-extra-stuff",
        })
        assert resp.status_code == 422


class TestEdgeCases:
    """Edge cases: boundary dates, very old birthdays, all categories."""

    def test_birthday_yesterday(self, client):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": yesterday,
            "categories": ["time_alive"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["age_days"] == 1

    def test_very_old_birthday(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "1900-01-01",
            "as_of": "2025-01-01",
            "categories": ["time_alive", "stars"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["age_years"] > 120
        assert data["stars_reached"] > 0

    def test_all_categories_explicit(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": [
                "time_alive", "moon", "light_sphere",
                "stars", "exoplanets", "star_classification",
                "planetary_ages", "body_stats", "cosmic_journey",
                "scale_comparisons", "universe_perspective",
                "voyagers", "eclipses", "links",
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "age_years" in data
        assert "moon_phase_at_midnight_utc" in data
        assert "light_sphere" in data
        assert "stars" in data
        assert "estimated_exoplanets" in data
        assert "star_type_breakdown" in data
        assert "planetary_ages" in data
        assert "body_stats" in data
        assert "cosmic_journey" in data
        assert "scale_comparisons" in data
        assert "universe_age_percent" in data
        assert "voyagers" in data
        assert "eclipses" in data
        assert "nasa_apod_url" in data
