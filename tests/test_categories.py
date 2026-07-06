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
        # Exact counts for 2000-01-01..2025-01-01; the catalogue
        # is checked in, so these are stable.
        assert ec["solar_eclipses"] == 56
        assert ec["lunar_eclipses"] == 57
        assert ec["total_eclipses"] == 113

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
        # A 25 ly sphere contains known planet hosts (Proxima,
        # GJ 876, Tau Ceti...), so zero would mean the matching
        # is broken.
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["exoplanets"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["estimated_exoplanets"] > 0
        assert data["potentially_habitable"] > 0
        assert (
            data["potentially_habitable"]
            < data["estimated_exoplanets"]
        )

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

    def test_sun_constellation(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-12-05",
            "as_of": "2025-01-01",
            "categories": ["sun_constellation"],
        })
        assert resp.status_code == 200
        data = resp.json()
        sc = data["sun_constellation"]
        assert sc["constellation"] == "Ophiuchus"
        assert sc["zodiac_sign"] == "Sagittarius"
        assert sc["matches_zodiac_sign"] is False
        assert "age_years" not in data

    def test_moon_includes_next_full_moon(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["moon"],
        })
        assert resp.status_code == 200
        # Real full moon: 2025-07-10.
        assert resp.json()["next_full_moon_date"] == "2025-07-10"

    def test_eclipses_include_next_dates(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-01-01",
            "as_of": "2025-01-01",
            "categories": ["eclipses"],
        })
        assert resp.status_code == 200
        ec = resp.json()["eclipses"]
        assert ec["next_solar_eclipse"] == "2025-03-29"
        assert ec["next_lunar_eclipse"] == "2025-03-14"

    def test_stars_reached_this_year(self, client):
        resp = client.post("/v1/big-endian-first-light", json={
            "birthday": "2000-06-15",
            "as_of": "2025-06-15",
            "categories": ["stars"],
            "star_limit": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        # Independently derived from the catalogue: stars in
        # the (radius - 1, radius] shell, with the radius
        # computed exactly as the engine computes it.
        from astropy import units as u
        from astropy.time import Time

        from src.compute import NEARBY_STARS

        radius = (
            (Time("2025-06-15") - Time("2000-06-15"))
            .to(u.yr).value
        )
        expected = sum(
            1 for s in NEARBY_STARS
            if radius - 1.0 < s["distance_ly"] <= radius
        )
        assert data["stars_reached_this_year"] == expected
        assert (
            data["stars_reached_this_year"]
            <= data["stars_reached"]
        )

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
