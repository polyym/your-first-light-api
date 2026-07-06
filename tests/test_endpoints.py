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


class TestRootIndex:
    """Verify the ``GET /`` discovery route."""

    def test_root_returns_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Your First Light"
        assert data["docs_url"] == "/docs"
        assert data["health_url"] == "/health"
        assert (
            "/v1/big-endian-first-light" in data["endpoints"]
        )
        assert len(data["endpoints"]) == 3

    def test_root_not_rate_limited(self, client):
        for _ in range(3):
            assert client.get("/").status_code == 200


class TestContractEdges:
    """Pin the unwritten edges of the request contract."""

    def test_ambiguous_date_middle_endian(self, client):
        """01/02/2003 is January 2nd in MM/DD/YYYY."""
        resp = client.post("/v1/middle-endian-first-light", json={
            "birthday": "01/02/2003",
            "as_of": "01/02/2023",
            "categories": ["time_alive"],
        })
        assert resp.status_code == 200
        assert resp.json()["birthday"] == "2003-01-02"

    def test_ambiguous_date_little_endian(self, client):
        """01/02/2003 is February 1st in DD/MM/YYYY."""
        resp = client.post("/v1/little-endian-first-light", json={
            "birthday": "01/02/2003",
            "as_of": "01/02/2023",
            "categories": ["time_alive"],
        })
        assert resp.status_code == 200
        assert resp.json()["birthday"] == "2003-02-01"

    def test_feb_29_leap_year_is_valid(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-02-29",
            "as_of": "2025-01-01",
            "categories": ["time_alive"],
        })
        assert resp.status_code == 200
        assert resp.json()["birthday"] == "2000-02-29"

    def test_feb_29_non_leap_year_is_rejected(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2001-02-29",
        })
        assert resp.status_code == 422

    def test_star_limit_lower_bound(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["stars"],
            "star_limit": 1,
        })
        assert resp.status_code == 200
        assert len(resp.json()["stars"]) == 1

    def test_star_limit_upper_bound(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["stars"],
            "star_limit": 50000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["stars"]) == data["stars_reached"]
        assert "stars_remaining" not in data

    @pytest.mark.parametrize("limit", [0, -1, 50001])
    def test_star_limit_out_of_bounds(self, client, limit):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "star_limit": limit,
        })
        assert resp.status_code == 422

    def test_empty_categories_rejected(self, client):
        """An explicit empty list is never silently 'everything'."""
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "categories": [],
        })
        assert resp.status_code == 422


class TestEdgeCases:
    """Edge cases: boundary dates, very old birthdays, all categories."""

    def test_birthday_yesterday(self, client):
        # Pin as_of so a midnight crossing between this line and
        # the handler cannot change the expected age.
        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": yesterday,
            "as_of": today.isoformat(),
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
                "sun_constellation",
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
        assert "sun_constellation" in data
