"""End-to-end tests covering the full request lifecycle."""


class TestHealthE2E:
    """End-to-end health check with data-load assertions."""

    def test_returns_loaded_counts(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["stars_loaded"] > 25000
        assert d["eclipses_loaded"] > 400


class TestFullRequest:
    """Verify a full request returns all expected categories."""

    def test_all_categories_populated(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
        })
        assert r.status_code == 200
        d = r.json()
        assert d["birthday"] == "2000-06-15"
        assert d["age_years"] == 25.0
        assert d["stars_reached"] > 0
        assert d["moon_phase_at_midnight_utc"]["phase_name"]
        assert d["eclipses"]["total_eclipses"] > 0
        assert len(d["voyagers"]) == 2
        assert len(d["planetary_ages"]) == 9
        assert len(d["scale_comparisons"]) == 8
        assert d["body_stats"]["thermal_power_watts"] > 50
        assert d["cosmic_journey"]["earth_orbits_completed"] > 0
        assert 0 < d["universe_age_percent"] < 1
        assert d["nasa_apod_url"].startswith("https://")
        assert len(d["star_type_breakdown"]) > 0
        assert d["estimated_exoplanets"] >= 0
        assert d["light_sphere"]["radius_ly"] == 25.0


class TestDateFormats:
    """Verify all three date format endpoints produce consistent results."""

    def test_middle_endian(self, client):
        r = client.post("/v1/middle-endian-first-light", json={
            "birthday": "06/15/2000",
            "as_of": "06/15/2025",
            "categories": ["time_alive"],
        })
        assert r.status_code == 200
        d = r.json()
        assert d["birthday"] == "2000-06-15"
        assert d["age_years"] == 25.0
        assert "stars" not in d

    def test_little_endian(self, client):
        r = client.post("/v1/little-endian-first-light", json={
            "birthday": "15/06/2000",
            "as_of": "15/06/2025",
            "categories": ["eclipses"],
        })
        assert r.status_code == 200
        d = r.json()
        assert d["birthday"] == "2000-06-15"
        assert d["eclipses"]["solar_eclipses"] > 0
        assert "age_years" not in d


class TestStarLimit:
    """Verify ``star_limit`` truncates the list but not the counts."""

    def test_limits_list_not_counts(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["stars"],
            "star_limit": 5,
        })
        assert r.status_code == 200
        d = r.json()
        assert len(d["stars"]) == 5
        assert d["stars_reached"] > 5
        assert d["next_star"] is not None
        assert "more star" in d["stars_remaining"]
        assert "furthest being" in d["stars_remaining"]

    def test_default_limit_applies(self, client):
        """Without star_limit, the schema default of 500 applies."""
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "1900-01-01",
            "as_of": "2025-06-15",
            "categories": ["stars"],
        })
        assert r.status_code == 200
        d = r.json()
        assert len(d["stars"]) <= 500
        if d["stars_reached"] > 500:
            assert "more star" in d["stars_remaining"]
            assert "furthest being" in d["stars_remaining"]

    def test_schema_default_is_500(self):
        """The Pydantic model defaults star_limit to 500."""
        from src.models import BigEndianRequest
        req = BigEndianRequest(birthday="2000-01-01")
        assert req.star_limit == 500

    def test_no_remaining_when_under_limit(self, client):
        """stars_remaining is absent when all stars fit."""
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "2020-06-15",
            "as_of": "2025-06-15",
            "categories": ["stars"],
        })
        assert r.status_code == 200
        d = r.json()
        assert d["stars_reached"] <= 500
        assert "stars_remaining" not in d


class TestValidationE2E:
    """End-to-end validation error tests."""

    def test_invalid_date(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "not-a-date",
        })
        assert r.status_code == 422

    def test_future_birthday(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "2099-01-01",
        })
        assert r.status_code == 422

    def test_birthday_equals_as_of(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2000-01-01",
        })
        assert r.status_code == 422


class TestRateLimitingE2E:
    """End-to-end rate limiting with header verification."""

    def test_retry_after_header(self, client):
        payload = {
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["links"],
        }
        r1 = client.post(
            "/v1/big-endian-first-light", json=payload,
        )
        assert r1.status_code == 200
        r2 = client.post(
            "/v1/big-endian-first-light", json=payload,
        )
        assert r2.status_code == 429
        assert "Retry-After" in r2.headers
        assert "Rate limited" in r2.json()["detail"]

    def test_different_ips_not_blocked(self, client):
        payload = {
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["links"],
        }
        r1 = client.post(
            "/v1/big-endian-first-light", json=payload,
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        r2 = client.post(
            "/v1/big-endian-first-light", json=payload,
            headers={"X-Forwarded-For": "2.2.2.2"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_spoof_resistance_rightmost_ip(self, client):
        """Spoofing the leftmost IP should not bypass the limit."""
        payload = {
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["links"],
        }
        r1 = client.post(
            "/v1/big-endian-first-light", json=payload,
            headers={"X-Forwarded-For": "spoofed-1, 3.3.3.3"},
        )
        r2 = client.post(
            "/v1/big-endian-first-light", json=payload,
            headers={"X-Forwarded-For": "spoofed-2, 3.3.3.3"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 429


class TestEclipseCoverageE2E:
    """Verify eclipse coverage notes through the API."""

    def test_no_note_for_normal_range(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["eclipses"],
        })
        assert r.status_code == 200
        ec = r.json()["eclipses"]
        assert "coverage_note" not in ec

    def test_note_for_pre_1900_birthday(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "1850-01-01",
            "as_of": "2025-01-01",
            "categories": ["eclipses"],
        })
        assert r.status_code == 200
        ec = r.json()["eclipses"]
        assert "coverage_note" in ec
        assert "1900-2100" in ec["coverage_note"]


class TestDataIntegrity:
    """Verify data catalogue integrity through the API."""

    def test_known_stars_present(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "1975-01-01",
            "as_of": "2025-06-15",
            "categories": ["stars"],
            "star_limit": 5000,
        })
        d = r.json()
        names = {s["name"] for s in d["stars"]}
        for star in [
            "Proxima Centauri", "Sirius A",
            "Barnard's Star", "Vega",
            "TRAPPIST-1", "Tau Ceti",
        ]:
            assert star in names, f"{star} missing"

    def test_no_duplicate_stars(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "1975-01-01",
            "as_of": "2025-06-15",
            "categories": ["stars"],
        })
        names = [s["name"] for s in r.json()["stars"]]
        assert len(names) == len(set(names))

    def test_proxima_distance(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "1975-01-01",
            "as_of": "2025-06-15",
            "categories": ["stars"],
        })
        proxima = [
            s for s in r.json()["stars"]
            if s["name"] == "Proxima Centauri"
        ][0]
        assert 4.2 < proxima["distance_ly"] < 4.3

    def test_eclipse_counts_consistent(self, client):
        r = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["eclipses"],
        })
        ec = r.json()["eclipses"]
        assert ec["solar_eclipses"] > 40
        assert ec["lunar_eclipses"] > 40
        assert ec["total_eclipses"] == (
            ec["solar_eclipses"] + ec["lunar_eclipses"]
        )
