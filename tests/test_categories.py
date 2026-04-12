"""Integration tests for individual response categories."""

import pytest


class TestIndividualCategories:
    """Integration tests for each response category in isolation."""

    def test_eclipses(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["eclipses"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "eclipses" in data
        ec = data["eclipses"]
        assert ec["solar_eclipses"] > 0
        assert ec["lunar_eclipses"] > 0
        assert ec["total_eclipses"] == (
            ec["solar_eclipses"] + ec["lunar_eclipses"]
        )

    def test_voyagers(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["voyagers"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "voyagers" in data
        assert len(data["voyagers"]) == 2
        v1 = data["voyagers"][0]
        assert v1["name"] == "Voyager 1"
        assert v1["was_launched_before_birth"]
        assert v1["distance_travelled_since_birth_km"] > 0

    def test_exoplanets(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["exoplanets"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "estimated_exoplanets" in data
        assert data["estimated_exoplanets"] >= 0
        assert "potentially_habitable" in data

    def test_body_stats(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["body_stats"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "body_stats" in data
        stats = data["body_stats"]
        assert stats["estimated_heartbeats"] > 0
        assert stats["estimated_breaths"] > 0
        assert stats["estimated_blinks"] > 0
        assert stats["photons_emitted"] > 0
        assert 50 < stats["thermal_power_watts"] < 200

    def test_cosmic_journey(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["cosmic_journey"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "cosmic_journey" in data
        j = data["cosmic_journey"]
        assert j["earth_distance_around_sun_km"] > 0
        assert j["earth_orbits_completed"] == pytest.approx(
            25.0, abs=0.1,
        )
        assert j["galactic_distance_km"] > 0
        assert j["galactic_orbit_degrees"] > 0
        assert j["great_attractor_distance_km"] > 0

    def test_scale_comparisons(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["scale_comparisons"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "scale_comparisons" in data
        assert len(data["scale_comparisons"]) == 8

    def test_universe_perspective(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["universe_perspective"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "universe_age_percent" in data
        assert 0 < data["universe_age_percent"] < 1

    def test_star_coordinates(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "1975-01-01",
            "as_of": "2025-06-15",
            "categories": ["stars"],
            "star_limit": 5000,
        })
        assert resp.status_code == 200
        data = resp.json()
        trappist = [
            s for s in data["stars"]
            if s["name"] == "TRAPPIST-1"
        ]
        assert len(trappist) == 1
        assert trappist[0]["ra_deg"] == pytest.approx(
            346.62, abs=0.1,
        )
        assert trappist[0]["dec_deg"] == pytest.approx(
            -5.04, abs=0.1,
        )

    def test_star_light_arrival_date(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["stars"],
        })
        assert resp.status_code == 200
        data = resp.json()
        proxima = [
            s for s in data["stars"]
            if s["name"] == "Proxima Centauri"
        ]
        assert len(proxima) == 1
        assert "light_arrival_date" in proxima[0]
        assert proxima[0]["light_arrival_date"].startswith(
            "2004",
        )
        assert "your_age_at_light_arrival_years" in proxima[0]
        assert proxima[0][
            "your_age_at_light_arrival_years"
        ] == pytest.approx(4.22, abs=0.05)

    def test_voyager_distance_accuracy(self, client):
        """Verify interpolated Voyager distances."""
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["voyagers"],
        })
        assert resp.status_code == 200
        data = resp.json()
        v1 = data["voyagers"][0]
        v2 = data["voyagers"][1]
        assert 85 < v1["distance_travelled_since_birth_au"] < 95
        assert 74 < v2["distance_travelled_since_birth_au"] < 84
