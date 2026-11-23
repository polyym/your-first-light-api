"""Integrity of the star and eclipse catalogues shipped in data/."""

import json
import math
from collections import Counter
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from first_light.facts.catalogues import DATA_DIR, DATA_MANIFEST, NEARBY_STARS
from tools.updaters.stars.merge import MERGE_MAX_MAG_DIFF
from tools.updaters.stars.validate import (
    DUPLICATE_DIST_TOL_FLOOR_LY,
    DUPLICATE_DIST_TOL_FRACTION,
    DUPLICATE_SEP_ARCSEC,
    validate_catalogue,
)

ECLIPSES = json.loads((DATA_DIR / "eclipses.json").read_text(encoding="utf-8"))
ECLIPSE_KINDS = pytest.mark.parametrize(
    "kind", ["solarEclipses", "lunarEclipses"], ids=["solar", "lunar"]
)
CATALOGUE_FIRST_DAY = date(1900, 1, 1)
CATALOGUE_LAST_DAY = date(2100, 12, 31)

# One star entering from two catalogues whose parallaxes disagree, by
# the thresholds of the updater's find_positional_duplicates, which
# takes over a second on the full catalogue.
TWIN_SEPARATION_DEG = DUPLICATE_SEP_ARCSEC / 3600

Star = dict[str, Any]


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


FIELD_RULES: dict[str, Callable[[Any], bool]] = {
    "name": lambda value: isinstance(value, str) and value.strip() != "",
    "distance_ly": lambda value: _is_finite_number(value) and value > 0,
    "spectral_type": lambda value: isinstance(value, str),
    "apparent_magnitude": _is_finite_number,
    "magnitude_band": lambda value: value in ("V", "G", None),
    "known_exoplanets": _is_count,
    "ra_deg": lambda value: (
        value is None or (_is_finite_number(value) and 0 <= value < 360)
    ),
    "dec_deg": lambda value: (
        value is None or (_is_finite_number(value) and -90 <= value <= 90)
    ),
}


def _separation_deg(star: Star, other: Star) -> float:
    ra_gap = (star["ra_deg"] - other["ra_deg"] + 180) % 360 - 180
    mean_dec = math.radians((star["dec_deg"] + other["dec_deg"]) / 2)
    return math.hypot(
        ra_gap * math.cos(mean_dec), star["dec_deg"] - other["dec_deg"]
    )


def _is_twin(star: Star, other: Star) -> bool:
    if set(star["sources"]) & set(other["sources"]):
        return False
    # Too far apart in brightness to be one star: a faint companion.
    magnitude_gap = star["apparent_magnitude"] - other["apparent_magnitude"]
    if abs(magnitude_gap) > MERGE_MAX_MAG_DIFF:
        return False
    nearer = min(star["distance_ly"], other["distance_ly"])
    tolerance = max(
        DUPLICATE_DIST_TOL_FLOOR_LY, DUPLICATE_DIST_TOL_FRACTION * nearer
    )
    return (
        _separation_deg(star, other) < TWIN_SEPARATION_DEG
        and abs(star["distance_ly"] - other["distance_ly"]) > tolerance
    )


def _twins(stars: list[Star]) -> list[tuple[str, str]]:
    placed = sorted(
        (
            star
            for star in stars
            if star["ra_deg"] is not None and star["dec_deg"] is not None
        ),
        key=lambda star: star["dec_deg"],
    )
    found = []
    for index, star in enumerate(placed):
        for later in range(index + 1, len(placed)):
            other = placed[later]
            if other["dec_deg"] - star["dec_deg"] >= TWIN_SEPARATION_DEG:
                break
            if _is_twin(star, other):
                found.append((star["name"], other["name"]))
    return found


def _eclipse_days(kind: str) -> list[date]:
    return [date.fromisoformat(day) for day in ECLIPSES[kind]]


def test_star_names_are_unique() -> None:
    counts = Counter(star["name"] for star in NEARBY_STARS)
    assert [name for name, count in counts.items() if count > 1] == []


def test_no_star_is_listed_twice_by_different_catalogues() -> None:
    assert _twins(NEARBY_STARS) == []


def test_shipped_catalogue_passes_the_updaters_own_checks() -> None:
    """The checks the updater runs before it writes the file.

    A catalogue written by an older updater can pass every other test
    here while breaking rules added since, such as the spectral types a
    star's brightness rules out.
    """
    assert validate_catalogue([dict(star) for star in NEARBY_STARS]) == []


@pytest.mark.parametrize(
    ("faint_magnitude", "is_twin"),
    [(9.0, True), (9.1, False)],
    ids=["5-mag-fainter", "5.1-mag-fainter"],
)
def test_far_fainter_neighbour_is_a_second_star(
    faint_magnitude: float, is_twin: bool
) -> None:
    """A bright star and a far fainter row beside it are two stars."""
    bright = {
        "sources": ["hipparcos"],
        "distance_ly": 50.0,
        "apparent_magnitude": 4.0,
        "ra_deg": 10.0,
        "dec_deg": 20.0,
    }
    faint = {
        **bright,
        "sources": ["gaia"],
        "distance_ly": 60.0,
        "apparent_magnitude": faint_magnitude,
    }
    assert _is_twin(bright, faint) is is_twin


@pytest.mark.parametrize("field", list(FIELD_RULES))
def test_every_star_has_a_usable_value_for_each_field_read(field: str) -> None:
    rule = FIELD_RULES[field]
    unusable = [
        star.get("name")
        for star in NEARBY_STARS
        if field not in star or not rule(star[field])
    ]
    assert unusable == []


def test_proxima_centauri_is_the_nearest_star() -> None:
    nearest = min(NEARBY_STARS, key=lambda star: star["distance_ly"])

    assert nearest["name"] == "Proxima Centauri"
    assert nearest["distance_ly"] == pytest.approx(4.2465, abs=0.01)


def test_barnards_star_is_at_its_published_distance() -> None:
    barnard = next(
        star for star in NEARBY_STARS if star["name"] == "Barnard's Star"
    )
    assert barnard["distance_ly"] == pytest.approx(5.963, abs=0.02)


@ECLIPSE_KINDS
def test_eclipse_dates_are_in_order_without_repeats(kind: str) -> None:
    days = _eclipse_days(kind)
    assert days == sorted(set(days))


@ECLIPSE_KINDS
def test_eclipse_dates_lie_within_1900_to_2100(kind: str) -> None:
    days = _eclipse_days(kind)
    assert min(days) >= CATALOGUE_FIRST_DAY
    assert max(days) <= CATALOGUE_LAST_DAY


@ECLIPSE_KINDS
def test_every_year_from_1900_to_2100_has_at_least_two_eclipses(
    kind: str,
) -> None:
    per_year = Counter(day.year for day in _eclipse_days(kind))
    years = range(CATALOGUE_FIRST_DAY.year, CATALOGUE_LAST_DAY.year + 1)
    assert [year for year in years if per_year[year] < 2] == []


def test_manifest_lists_both_data_files() -> None:
    assert set(DATA_MANIFEST["files"]) == {"eclipses.json", "stars.json"}


@pytest.mark.parametrize("name", ["eclipses.json", "stars.json"])
def test_manifest_gives_the_day_each_file_changed(name: str) -> None:
    updated = DATA_MANIFEST["files"][name]["updated"]
    assert date.fromisoformat(updated).isoformat() == updated
