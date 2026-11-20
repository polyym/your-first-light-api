"""Properties every answer keeps, checked on the real app and data."""

import math
import re
from collections import Counter
from collections.abc import Iterator
from itertools import pairwise
from typing import Any

import pytest
from fastapi.testclient import TestClient

from first_light.web import rate_limit

BIG_ENDIAN = "/v1/big-endian-first-light"
# The largest whole number a JavaScript client reads without rounding.
MAX_SAFE_INTEGER = 2**53 - 1
# A date after 9999 is written with a five-digit year.
DATE = re.compile(r"\d{4,5}-\d{2}-\d{2}")
DATE_FIELDS = ("birthday", "as_of", "next_solar_eclipse", "next_lunar_eclipse")
# On either side of UTC's backward steps, a leap second, the catalogue of
# eclipses and the calendar.
AS_OF_STEPS = (
    "1961-08-01",
    "1961-08-02",
    "1968-02-01",
    "1968-02-02",
    "1972-07-01",
    "2017-01-01",
    "2026-11-18",
    "2100-12-31",
    "2101-01-01",
    "9999-12-31",
)
COUNTS_UP = (
    "age_years",
    "age_days",
    "age_hours",
    "age_minutes",
    "age_seconds",
    "earth_rotations",
    "leap_years_lived_through",
    "stars_reached",
    "naked_eye_stars_reached",
    "estimated_exoplanets",
)


def _answer(client: TestClient, **request: object) -> dict[str, Any]:
    """Posts a request as a caller with no wait and returns the body."""
    rate_limit._last_request.clear()
    response = client.post(BIG_ENDIAN, json=request)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _leaves(value: object, key: str = "") -> Iterator[tuple[str, object]]:
    """Gives every scalar in a body with the key it sits under."""
    if isinstance(value, dict):
        for name, inner in value.items():
            yield from _leaves(inner, name)
    elif isinstance(value, list):
        for inner in value:
            yield from _leaves(inner, key)
    else:
        yield key, value


@pytest.mark.parametrize(
    "birthday", ["0001-01-01", "1961-07-31", "1977-08-30", "1998-11-15"]
)
def test_counts_never_fall_as_as_of_grows(
    client: TestClient, birthday: str
) -> None:
    answers = [
        _answer(
            client,
            birthday=birthday,
            as_of=as_of,
            categories=["time_alive", "stars", "exoplanets", "eclipses"],
            star_limit=1,
        )
        for as_of in AS_OF_STEPS
        if as_of > birthday
    ]

    for earlier, later in pairwise(answers):
        fell = [name for name in COUNTS_UP if later[name] < earlier[name]]
        assert fell == [], later["as_of"]
        assert later["age_seconds"] > earlier["age_seconds"]
        assert (
            later["eclipses"]["total_eclipses"]
            >= earlier["eclipses"]["total_eclipses"]
        )


@pytest.mark.parametrize(
    ("birthday", "star_limit"),
    [
        pytest.param("2026-11-17", 500, id="none-reached"),
        pytest.param("1998-11-15", 500, id="all-listed"),
        pytest.param("1998-11-15", 1, id="one-listed"),
        pytest.param("1950-01-01", 500, id="list-cut-short"),
        pytest.param("1850-01-01", 50_000, id="whole-catalogue"),
    ],
)
def test_star_list_agrees_with_the_counts(
    client: TestClient, birthday: str, star_limit: int
) -> None:
    body = _answer(
        client,
        birthday=birthday,
        as_of="2026-11-18",
        categories=[
            "light_sphere",
            "stars",
            "exoplanets",
            "star_classification",
        ],
        star_limit=star_limit,
    )
    listed = body["stars"]
    reached = body["stars_reached"]
    distances = [star["distance_ly"] for star in listed]

    assert len(listed) == min(star_limit, reached)
    assert distances == sorted(distances)
    assert all(d <= body["light_sphere"]["radius_ly"] for d in distances)
    assert all(star["light_arrival_date"] <= body["as_of"] for star in listed)
    assert ("stars_remaining" in body) == (reached > star_limit)
    assert sum(body["star_type_breakdown"].values()) == reached
    if reached <= star_limit:
        assert body["star_type_breakdown"] == Counter(
            star["spectral_class"] for star in listed
        )
        assert body["estimated_exoplanets"] == sum(
            star["known_exoplanets"] for star in listed
        )
        assert body["naked_eye_stars_reached"] == sum(
            star["naked_eye_visible"] for star in listed
        )


@pytest.mark.parametrize(
    ("birthday", "as_of"),
    [
        pytest.param("0001-01-01", "0001-01-02", id="first-day"),
        pytest.param("0001-01-01", "9999-12-31", id="longest"),
        pytest.param("9999-12-30", "9999-12-31", id="last-day"),
    ],
)
def test_extreme_lifetimes_give_numbers_and_dates_any_client_can_read(
    client: TestClient, birthday: str, as_of: str
) -> None:
    body = _answer(client, birthday=birthday, as_of=as_of, star_limit=1)

    for key, value in _leaves(body):
        if isinstance(value, float):
            assert math.isfinite(value), key
        elif isinstance(value, int):
            assert abs(value) <= MAX_SAFE_INTEGER, key
        elif key in DATE_FIELDS or key.endswith("_date"):
            assert isinstance(value, str) and DATE.fullmatch(value), key
