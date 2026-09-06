"""Tests for the v1.1.3 API hardening: body limits, HEAD support,
health status codes, friendlier body errors and the documented
time_alive semantics."""

import math
from datetime import date

import pytest
from fastapi.testclient import TestClient

import src.app as app_module
import src.compute as compute
from src.app import MAX_BODY_BYTES, app
from src.compute import compute_first_light
from src.constants import (
    VOYAGER_1_MILESTONES,
    VOYAGER_1_SPEED_KM_S,
    VOYAGER_2_MILESTONES,
)

PATH = "/v1/big-endian-first-light"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestBodySizeLimit:
    """Oversized request bodies are refused before parsing."""

    def test_declared_oversize_body_is_413(self, client):
        payload = (
            b'{"birthday": "2000-01-01", "pad": "'
            + b"x" * (MAX_BODY_BYTES + 1024)
            + b'"}'
        )
        r = client.post(
            PATH, content=payload,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413
        assert isinstance(r.json()["detail"], str)
        assert "64 KB" in r.json()["detail"]

    def test_chunked_oversize_body_is_413(self, client):
        """A streamed body without Content-Length is counted as
        it arrives and cut off at the limit."""
        def chunks():
            yield b'{"birthday": "2000-01-01", "pad": "'
            for _ in range(80):
                yield b"x" * 1024
            yield b'"}'

        r = client.post(
            PATH, content=chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413

    def test_chunked_small_body_is_accepted(self, client):
        def chunks():
            yield b'{"birthday": "2000-01-01", '
            yield b'"categories": ["links"]}'

        r = client.post(
            PATH, content=chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["birthday"] == "2000-01-01"

    def test_413_refunds_rate_limit_slot(self, client):
        payload = b'{"pad": "' + b"x" * (MAX_BODY_BYTES + 1) + b'"}'
        r = client.post(
            PATH, content=payload,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413
        r = client.post(
            PATH, json={"birthday": "2000-01-01", "categories": ["links"]},
        )
        assert r.status_code == 200

    def test_413_carries_cors_headers(self, client):
        payload = b'{"pad": "' + b"x" * (MAX_BODY_BYTES + 1) + b'"}'
        r = client.post(
            PATH, content=payload,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://example.com",
            },
        )
        assert r.status_code == 413
        assert r.headers["access-control-allow-origin"] == "*"

    def test_limit_is_documented(self, client):
        spec = client.get("/openapi.json").json()
        responses = spec["paths"][PATH]["post"]["responses"]
        assert "413" in responses
        assert "500" in responses


class TestHeadAndHealth:
    def test_head_health(self, client):
        r = client.head("/health")
        assert r.status_code == 200
        assert r.content == b""

    def test_head_index(self, client):
        assert client.head("/").status_code == 200

    def test_health_is_503_when_catalogue_empty(
        self, client, monkeypatch,
    ):
        monkeypatch.setattr(app_module, "NEARBY_STARS", [])
        r = client.get("/health")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"
        assert r.json()["stars_loaded"] == 0


class TestBodyErrorMessages:
    """Malformed bodies get a plain-English detail string."""

    def test_invalid_json(self, client):
        r = client.post(
            PATH, content=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422
        assert r.json()["detail"] == "Request body is not valid JSON."

    def test_empty_body(self, client):
        r = client.post(
            PATH, content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422
        assert r.json()["detail"] == "Request body is required."

    def test_array_body(self, client):
        r = client.post(PATH, json=[1, 2])
        assert r.status_code == 422
        assert r.json()["detail"] == (
            "Request body must be a JSON object."
        )

    def test_field_errors_keep_field_name(self, client):
        r = client.post(PATH, json={"as_of": "2020-01-01"})
        assert r.status_code == 422
        assert r.json()["detail"] == "birthday: Field required"


class TestTimeAliveSemantics:
    """The README example, including its five leap seconds."""

    def test_readme_example(self, client):
        r = client.post(PATH, json={
            "birthday": "2002-10-14",
            "as_of": "2026-04-11",
            "categories": ["time_alive", "links"],
        })
        assert r.status_code == 200
        body = r.json()
        assert body["age_years"] == 23.49
        assert body["age_days"] == 8580
        assert body["age_hours"] == 205920
        assert body["age_minutes"] == 12355200
        # Five leap seconds were inserted between the two dates.
        assert body["age_seconds"] == 8580 * 86400 + 5
        assert body["earth_rotations"] == 8603.49
        assert body["leap_years_lived_through"] == 6
        assert body["nasa_apod_url"] == (
            "https://apod.nasa.gov/apod/ap021014.html"
        )

    def test_age_days_is_calendar_arithmetic(self):
        result = compute_first_light(
            date(1960, 6, 30), date(2026, 9, 6), {"time_alive"},
        )
        assert result.age_days == (
            date(2026, 9, 6) - date(1960, 6, 30)
        ).days
        assert result.age_seconds is not None
        assert result.age_seconds >= result.age_days * 86400
        assert result.age_hours == result.age_seconds // 3600
        assert result.age_minutes == result.age_seconds // 60


class TestVoyagerMilestones:
    """Milestones agree with JPL Horizons heliocentric ranges."""

    @staticmethod
    def _range(x: float, y: float, z: float) -> float:
        return math.sqrt(x * x + y * y + z * z)

    def test_2026_milestones_match_horizons(self):
        # JPL Horizons vectors (AU, heliocentric) for 2026-01-01.
        v1 = self._range(-31.83641396, -134.6784849, 97.44480620)
        v2 = self._range(39.22753201, -103.9915497, -87.91865807)
        assert dict(VOYAGER_1_MILESTONES)[date(2026, 1, 1)] == round(v1, 2)
        assert dict(VOYAGER_2_MILESTONES)[date(2026, 1, 1)] == round(v2, 2)

    def test_milestones_are_sorted_and_increasing(self):
        for table in (VOYAGER_1_MILESTONES, VOYAGER_2_MILESTONES):
            dates = [d for d, _ in table]
            dists = [a for _, a in table]
            assert dates == sorted(dates)
            assert dists == sorted(dists)

    def test_extrapolation_matches_horizons_2026_09(self):
        """Horizons range on 2026-09-06: 171.67 AU (V1), 143.87 AU
        (V2); the table extrapolation must be within 0.05 AU."""
        birth = date(2026, 1, 1)
        ref = date(2026, 9, 6)
        v1_since = compute.compute_voyager_status(birth, ref)
        v1 = v1_since[0].distance_travelled_since_birth_au
        v2 = v1_since[1].distance_travelled_since_birth_au
        assert abs((169.26 + v1) - 171.67) < 0.05
        assert abs((141.71 + v2) - 143.87) < 0.05


class TestScaleComparisonLabels:
    def test_voyager_label_uses_constant(self):
        result = compute_first_light(
            date(1990, 1, 1), date(2026, 9, 6), {"scale_comparisons"},
        )
        assert result.scale_comparisons is not None
        labels = [c.label for c in result.scale_comparisons]
        assert any(
            f"({VOYAGER_1_SPEED_KM_S:g} km/s)" in lab for lab in labels
        )
