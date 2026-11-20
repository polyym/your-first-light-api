"""Tests for building a response from the categories asked for."""

from datetime import date
from typing import Any

import pytest

from first_light.facts import stars
from first_light.facts.compute import compute_first_light
from first_light.models import ALL_CATEGORIES, FirstLightResponse

BIRTH = date(2000, 1, 1)
AS_OF = date(2010, 1, 1)

FIELDS = {
    "time_alive": {
        "age_years",
        "age_days",
        "age_hours",
        "age_minutes",
        "age_seconds",
        "earth_rotations",
        "leap_years_lived_through",
    },
    "moon": {
        "moon_phase_at_midnight_utc",
        "full_moons_since_birth",
        "next_full_moon_date",
    },
    "light_sphere": {"light_sphere", "speed_of_light_km_s"},
    "stars": {
        "stars_reached",
        "naked_eye_stars_reached",
        "stars_reached_this_year",
        "stars_remaining",
        "birthday_star",
        "stars",
        "next_star",
    },
    "exoplanets": {"estimated_exoplanets", "potentially_habitable"},
    "star_classification": {"star_type_breakdown"},
    "planetary_ages": {"planetary_ages"},
    "body_stats": {"body_stats"},
    "cosmic_journey": {"cosmic_journey"},
    "scale_comparisons": {"scale_comparisons"},
    "universe_perspective": {"universe_age_percent"},
    "voyagers": {"voyagers"},
    "eclipses": {"eclipses"},
    "links": {"nasa_apod_url"},
    "sun_constellation": {"sun_constellation"},
}


def _star(name: str, distance_ly: float) -> dict[str, Any]:
    return {
        "name": name,
        "distance_ly": distance_ly,
        "spectral_type": "G2V",
        "apparent_magnitude": 5.0,
        "magnitude_band": "V",
        "known_exoplanets": 1,
        "ra_deg": 0.0,
        "dec_deg": 0.0,
    }


@pytest.fixture(autouse=True)
def catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives a ten-year lifetime a value for every stars field.

    Three stars reached and, half a light-year beyond them, the next
    star, which is also the birthday star.
    """
    monkeypatch.setattr(
        stars,
        "NEARBY_STARS",
        [
            _star("Inner", 2.0),
            _star("Middle", 5.0),
            _star("Third", 9.0),
            _star("Outer", 10.5),
        ],
    )


def _filled(result: FirstLightResponse) -> set[str]:
    return {name for name, value in result if value is not None}


@pytest.mark.parametrize("category", sorted(ALL_CATEGORIES))
def test_each_category_fills_its_own_fields_and_no_others(
    category: str,
) -> None:
    result = compute_first_light(BIRTH, AS_OF, {category}, star_limit=1)

    assert _filled(result) == {"birthday", "as_of"} | FIELDS[category]


def test_no_categories_fills_only_birthday_and_as_of() -> None:
    result = compute_first_light(BIRTH, AS_OF, set(), star_limit=1)

    assert result.model_dump(exclude_none=True) == {
        "birthday": "2000-01-01",
        "as_of": "2010-01-01",
    }


def test_all_categories_together_equal_each_category_alone() -> None:
    together = compute_first_light(BIRTH, AS_OF, ALL_CATEGORIES, star_limit=1)
    alone: dict[str, Any] = {}
    for category in sorted(ALL_CATEGORIES):
        single = compute_first_light(BIRTH, AS_OF, {category}, star_limit=1)
        alone.update(single.model_dump(exclude_none=True))

    assert together.model_dump(exclude_none=True) == alone


def test_star_limit_is_forwarded_to_the_stars_list() -> None:
    result = compute_first_light(BIRTH, AS_OF, {"stars"}, star_limit=2)

    assert result.stars is not None
    assert [star.name for star in result.stars] == ["Inner", "Middle"]


def test_star_categories_cover_the_stars_within_the_age() -> None:
    result = compute_first_light(
        BIRTH,
        AS_OF,
        {"stars", "exoplanets", "star_classification"},
        star_limit=1,
    )

    assert (
        result.stars_reached,
        result.estimated_exoplanets,
        result.star_type_breakdown,
    ) == (3, 3, {"Sun-like (G)": 3})
