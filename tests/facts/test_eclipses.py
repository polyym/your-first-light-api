"""Tests for eclipse counts, the next eclipses and the coverage note."""

from datetime import date

import pytest

from first_light.facts import eclipses
from first_light.facts.age import measure_lifetime
from first_light.models import EclipseCounts, FirstLightResponse

COVERS = "Eclipse data covers 1900-2100."


@pytest.fixture
def small_catalogue(monkeypatch):
    """Replaces the catalogue with three solar and two lunar eclipses."""
    monkeypatch.setattr(
        eclipses,
        "SOLAR_ECLIPSE_DATES",
        (date(2000, 1, 10), date(2000, 2, 10), date(2000, 3, 10)),
    )
    monkeypatch.setattr(
        eclipses,
        "LUNAR_ECLIPSE_DATES",
        (date(2000, 1, 25), date(2000, 2, 25)),
    )


@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        pytest.param(
            date(2000, 1, 10),
            date(2000, 3, 10),
            (3, 2, 5),
            id="ends-on-eclipses",
        ),
        pytest.param(
            date(2000, 1, 11),
            date(2000, 3, 9),
            (1, 2, 3),
            id="ends-a-day-inside",
        ),
        pytest.param(
            date(2000, 1, 9),
            date(2000, 3, 11),
            (3, 2, 5),
            id="ends-a-day-outside",
        ),
        pytest.param(
            date(2000, 1, 11),
            date(2000, 1, 24),
            (0, 0, 0),
            id="between-eclipses",
        ),
        pytest.param(
            date(2000, 2, 10), date(2000, 2, 10), (1, 0, 1), id="single-day"
        ),
    ],
)
def test_eclipses_counted_with_both_ends_included(
    small_catalogue, birth, as_of, expected
):
    counts = eclipses.count_eclipses(birth, as_of)

    assert (
        counts.solar_eclipses,
        counts.lunar_eclipses,
        counts.total_eclipses,
    ) == expected


@pytest.mark.parametrize(
    ("as_of", "next_solar", "next_lunar"),
    [
        pytest.param(
            date(2000, 2, 9), "2000-02-10", "2000-02-25", id="day-before"
        ),
        pytest.param(
            date(2000, 2, 10), "2000-03-10", "2000-02-25", id="on-an-eclipse"
        ),
        pytest.param(date(2000, 2, 25), "2000-03-10", None, id="last-lunar"),
        pytest.param(date(2000, 3, 10), None, None, id="last-solar"),
    ],
)
def test_next_eclipse_is_strictly_after_as_of(
    small_catalogue, as_of, next_solar, next_lunar
):
    counts = eclipses.count_eclipses(date(1999, 12, 1), as_of)

    assert (counts.next_solar_eclipse, counts.next_lunar_eclipse) == (
        next_solar,
        next_lunar,
    )


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        pytest.param(date(1899, 12, 30), (None, None), id="1899-12-30"),
        pytest.param(
            date(1899, 12, 31), ("1900-01-01", "1900-01-02"), id="1899-12-31"
        ),
    ],
)
def test_next_eclipses_left_out_before_the_catalogue_can_tell_them(
    monkeypatch, as_of, expected
):
    monkeypatch.setattr(eclipses, "SOLAR_ECLIPSE_DATES", (date(1900, 1, 1),))
    monkeypatch.setattr(eclipses, "LUNAR_ECLIPSE_DATES", (date(1900, 1, 2),))

    counts = eclipses.count_eclipses(date(1850, 1, 1), as_of)

    assert (counts.next_solar_eclipse, counts.next_lunar_eclipse) == expected


@pytest.mark.parametrize(
    ("birth", "as_of"),
    [
        pytest.param(date(1900, 1, 1), date(2100, 12, 31), id="exactly"),
        pytest.param(date(1988, 3, 21), date(2026, 11, 18), id="inside"),
    ],
)
def test_no_coverage_note_when_lifetime_inside_catalogue(birth, as_of):
    assert eclipses.count_eclipses(birth, as_of).coverage_note is None


@pytest.mark.parametrize(
    ("birth", "as_of", "covered"),
    [
        pytest.param(
            date(1899, 12, 31),
            date(2000, 1, 1),
            "1900-01-01 to 2000-01-01",
            id="born-a-day-before",
        ),
        pytest.param(
            date(2000, 1, 1),
            date(2101, 1, 1),
            "2000-01-01 to 2100-12-31",
            id="as-of-a-day-after",
        ),
        pytest.param(
            date(1850, 1, 1),
            date(2150, 1, 1),
            "1900-01-01 to 2100-12-31",
            id="both-ends-outside",
        ),
        pytest.param(
            date(1850, 1, 1),
            date(1900, 1, 1),
            "1900-01-01 to 1900-01-01",
            id="first-day-only",
        ),
        pytest.param(
            date(2100, 12, 31),
            date(2150, 1, 1),
            "2100-12-31 to 2100-12-31",
            id="last-day-only",
        ),
    ],
)
def test_coverage_note_names_the_covered_part(birth, as_of, covered):
    assert eclipses.count_eclipses(birth, as_of).coverage_note == (
        f"{COVERS} Counts reflect only the covered portion of your "
        f"lifetime ({covered})."
    )


@pytest.mark.parametrize(
    ("birth", "as_of"),
    [
        pytest.param(date(1800, 3, 1), date(1850, 1, 1), id="before"),
        pytest.param(date(1850, 1, 1), date(1899, 12, 31), id="up-to-1899"),
        pytest.param(date(2101, 1, 1), date(2200, 1, 1), id="after"),
    ],
)
def test_coverage_note_when_lifetime_wholly_outside(birth, as_of):
    assert eclipses.count_eclipses(birth, as_of).coverage_note == (
        f"{COVERS} None of your lifetime falls within it."
    )


def test_shipped_catalogue_gives_recorded_counts_and_next_eclipses():
    assert eclipses.count_eclipses(
        date(1988, 3, 21), date(2026, 11, 18)
    ) == EclipseCounts(
        solar_eclipses=84,
        lunar_eclipses=87,
        total_eclipses=171,
        next_solar_eclipse="2027-02-06",
        next_lunar_eclipse="2027-02-20",
    )


def test_add_eclipses_counts_from_birth_to_as_of(small_catalogue):
    birth, as_of = date(2000, 1, 10), date(2000, 2, 9)
    result = FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )

    eclipses.add_eclipses(result, measure_lifetime(birth, as_of))

    assert result.eclipses == EclipseCounts(
        solar_eclipses=1,
        lunar_eclipses=1,
        total_eclipses=2,
        next_solar_eclipse="2000-02-10",
        next_lunar_eclipse="2000-02-25",
    )
