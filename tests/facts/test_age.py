"""Tests for the lifetime and the categories built from it."""

from datetime import date

import pytest

from first_light.facts.age import (
    add_planetary_ages,
    add_time_alive,
    measure_lifetime,
)
from first_light.models import FirstLightResponse


def _empty_response(birth, as_of):
    return FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )


def test_readme_lifetime_includes_six_leap_seconds():
    life = measure_lifetime(date(1998, 11, 15), date(2026, 4, 11))

    assert (life.days, life.seconds) == (10_009, 864_777_606)


@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        pytest.param(
            date(2017, 1, 1), date(2017, 1, 2), 86_400, id="ordinary-day"
        ),
        pytest.param(
            date(2015, 6, 30), date(2015, 7, 1), 86_401, id="leap-second-2015"
        ),
        pytest.param(
            date(2016, 12, 31),
            date(2017, 1, 1),
            86_401,
            id="leap-second-2016",
        ),
        pytest.param(
            date(1972, 1, 1),
            date(2026, 11, 18),
            20_045 * 86_400 + 27,
            id="every-leap-second-since-1972",
        ),
        # TAI-UTC was 3.54 s on 1 January 1965 and is 37 s now.
        pytest.param(
            date(1965, 1, 1),
            date(2026, 11, 18),
            22_601 * 86_400 + 33,
            id="part-second-offset-before-1972",
        ),
        # astropy gives 1852934430.739 s; the part second is not counted.
        pytest.param(
            date(1968, 3, 1),
            date(2026, 11, 18),
            21_446 * 86_400 + 30,
            id="part-second-left-over-before-1972",
        ),
        # astropy gives 1553212820.9999998 s, just short of the second.
        pytest.param(
            date(1977, 8, 30),
            date(2026, 11, 18),
            17_977 * 86_400 + 21,
            id="from-1977",
        ),
    ],
)
def test_lifetime_seconds_count_leap_seconds(birth, as_of, expected):
    assert measure_lifetime(birth, as_of).seconds == expected


def test_minutes_leave_out_a_part_minute_of_extra_seconds():
    life = measure_lifetime(date(1965, 1, 1), date(2026, 11, 18))

    assert life.minutes == 22_601 * 24 * 60


@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        pytest.param(
            date(2017, 1, 1), date(2017, 1, 2), 1 / 365.25, id="one-day"
        ),
        pytest.param(
            date(2017, 1, 1), date(2021, 1, 1), 4.0, id="four-calendar-years"
        ),
    ],
)
def test_lifetime_years_are_julian_years(birth, as_of, expected):
    assert measure_lifetime(birth, as_of).years == pytest.approx(
        expected, rel=1e-12
    )


@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        pytest.param(
            date(1998, 11, 15),
            date(2026, 4, 11),
            {
                "age_years": 27.4,
                "age_days": 10_009,
                "age_hours": 240_216,
                "age_minutes": 14_412_960,
                "age_seconds": 864_777_606,
                "earth_rotations": 10_036.4,
                "leap_years_lived_through": 7,
            },
            id="readme",
        ),
        pytest.param(
            date(1988, 3, 21),
            date(2026, 11, 18),
            {
                "age_years": 38.66,
                "age_days": 14_121,
                "age_hours": 338_904,
                "age_minutes": 20_334_240,
                "age_seconds": 1_220_054_413,
                "earth_rotations": 14_159.66,
                "leap_years_lived_through": 9,
            },
            id="born-1988",
        ),
        # Two millennia make a wrong sidereal day show in earth_rotations.
        pytest.param(
            date(1, 1, 1),
            date(2026, 11, 18),
            {
                "age_years": 2025.84,
                "age_days": 739_937,
                "age_hours": 17_758_488,
                "age_minutes": 1_065_509_280,
                "age_seconds": 63_930_556_837,
                "earth_rotations": 741_962.88,
                "leap_years_lived_through": 491,
            },
            id="born-year-1",
        ),
    ],
)
def test_time_alive_matches_recorded_responses(birth, as_of, expected):
    result = _empty_response(birth, as_of)

    add_time_alive(result, measure_lifetime(birth, as_of))

    assert result.model_dump(include=set(expected)) == expected


def test_time_alive_counts_29_february_on_as_of():
    birth, as_of = date(2000, 2, 29), date(2024, 2, 29)
    result = _empty_response(birth, as_of)

    add_time_alive(result, measure_lifetime(birth, as_of))

    assert result.leap_years_lived_through == 7


def test_planetary_ages_list_mercury_to_pluto():
    birth, as_of = date(1988, 3, 21), date(2026, 11, 18)
    result = _empty_response(birth, as_of)

    add_planetary_ages(result, measure_lifetime(birth, as_of))

    assert [age.planet for age in result.planetary_ages] == [
        "Mercury",
        "Venus",
        "Earth",
        "Mars",
        "Jupiter",
        "Saturn",
        "Uranus",
        "Neptune",
        "Pluto",
    ]


@pytest.mark.parametrize(
    ("planet", "orbital_period", "age"),
    [
        ("Mercury", 87.97, 160.52),
        ("Venus", 224.7, 62.84),
        ("Earth", 365.25, 38.66),
        ("Mars", 687.0, 20.55),
        ("Jupiter", 4332.59, 3.26),
        ("Saturn", 10_755.7, 1.31),
        ("Uranus", 30_688.5, 0.46),
        ("Neptune", 60_195.0, 0.23),
        ("Pluto", 90_560.0, 0.16),
    ],
)
def test_planetary_age_is_days_lived_over_orbital_period(
    planet, orbital_period, age
):
    birth, as_of = date(1988, 3, 21), date(2026, 11, 18)
    result = _empty_response(birth, as_of)

    add_planetary_ages(result, measure_lifetime(birth, as_of))

    by_name = {entry.planet: entry for entry in result.planetary_ages}
    assert (
        by_name[planet].orbital_period_earth_days,
        by_name[planet].age,
    ) == (orbital_period, age)
