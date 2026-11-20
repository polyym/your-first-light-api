"""Tests for the Moon's phase, full moons since birth and the next one."""

import re
from datetime import date, timedelta

import pytest
from astropy.time import Time

from first_light.facts import moon
from first_light.facts.age import measure_lifetime
from first_light.models import FirstLightResponse, MoonPhaseAtBirth


# Published instants (UTC): new moon 2025-02-28 00:45, first quarter
# 2025-04-05 02:15, full moon 2025-04-13 00:22, third quarter 2025-04-21
# 01:36.
@pytest.mark.parametrize(
    ("day", "minutes_before", "phase_age"),
    [
        pytest.param(date(2025, 2, 28), 45, 29.5306, id="new"),
        pytest.param(date(2025, 4, 5), 135, 7.3826, id="first-quarter"),
        pytest.param(date(2025, 4, 13), 22, 14.7653, id="full"),
        pytest.param(date(2025, 4, 21), 96, 22.1479, id="third-quarter"),
    ],
)
def test_moon_age_is_place_in_a_mean_month(day, minutes_before, phase_age):
    expected = phase_age - minutes_before / (24 * 60)

    assert moon.moon_phase(day).moon_age_days == pytest.approx(
        expected, abs=0.03
    )


@pytest.mark.parametrize(
    ("day", "name"),
    [
        pytest.param(date(2025, 2, 28), "New Moon", id="new"),
        pytest.param(date(2025, 4, 5), "First Quarter", id="first-quarter"),
        pytest.param(date(2025, 4, 13), "Full Moon", id="full"),
        pytest.param(date(2025, 4, 21), "Third Quarter", id="third-quarter"),
    ],
)
def test_principal_phase_named_hours_before_its_instant(day, name):
    assert moon.moon_phase(day).phase_name == name


# Midnights within 0.03 days of a threshold, with the names clients get.
@pytest.mark.parametrize(
    ("day", "name"),
    [
        pytest.param(date(2024, 6, 7), "New Moon", id="below-0.5"),
        pytest.param(date(2013, 11, 4), "Waxing Crescent", id="above-0.5"),
        pytest.param(date(2005, 9, 11), "Waxing Crescent", id="below-6.88"),
        pytest.param(date(2009, 1, 4), "First Quarter", id="above-6.88"),
        pytest.param(date(1922, 5, 5), "First Quarter", id="below-7.88"),
        pytest.param(date(2011, 4, 12), "Waxing Gibbous", id="above-7.88"),
        pytest.param(date(2003, 3, 18), "Waxing Gibbous", id="below-14.27"),
        pytest.param(date(2015, 12, 25), "Full Moon", id="above-14.27"),
        pytest.param(date(2016, 11, 15), "Full Moon", id="below-15.27"),
        pytest.param(date(2005, 1, 26), "Waning Gibbous", id="above-15.27"),
        pytest.param(date(2007, 12, 1), "Waning Gibbous", id="below-21.65"),
        pytest.param(date(2011, 3, 26), "Third Quarter", id="above-21.65"),
        pytest.param(date(2025, 3, 23), "Third Quarter", id="below-22.65"),
        pytest.param(date(1955, 4, 16), "Waning Crescent", id="above-22.65"),
        pytest.param(date(2000, 2, 5), "Waning Crescent", id="below-29.03"),
        pytest.param(date(2026, 2, 17), "New Moon", id="above-29.03"),
    ],
)
def test_phase_name_changes_at_each_threshold(day, name):
    assert moon.moon_phase(day).phase_name == name


# Published instants (UTC): first quarter 2025-01-06 23:56, new moon
# 2025-02-28 00:45, full moon 2025-04-13 00:22. The lit share is JPL
# Horizons' for the Earth's centre at 00:00 UT: at a quarter the Moon
# stands at a right angle to the Sun, which lights a little over half
# the disc we see.
@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(2025, 2, 28), 0.02, id="45-min-before-new"),
        pytest.param(date(2025, 1, 7), 50.16, id="4-min-after-first-quarter"),
        pytest.param(date(2025, 4, 13), 99.96, id="22-min-before-full"),
        pytest.param(date(2026, 11, 17), 45.37, id="waxing"),
        pytest.param(date(2024, 12, 20), 76.96, id="waning"),
    ],
)
def test_illumination_near_new_quarter_and_full(day, expected):
    assert moon.moon_phase(day).illumination_percent == pytest.approx(
        expected, abs=0.06
    )


@pytest.mark.parametrize(
    ("day", "name", "illumination", "age"),
    [
        pytest.param(
            date(1993, 3, 8), "Full Moon", 99.6, 14.29, id="1993-03-08"
        ),
        pytest.param(
            date(2024, 12, 20), "Waning Gibbous", 77.0, 19.48, id="2024-12-20"
        ),
        pytest.param(
            date(1988, 3, 21), "Waxing Crescent", 11.5, 3.23, id="1988-03-21"
        ),
        pytest.param(
            date(2026, 11, 17), "First Quarter", 45.4, 6.93, id="2026-11-17"
        ),
        pytest.param(
            date(1900, 1, 1), "Waning Crescent", 0.5, 28.9, id="1900-01-01"
        ),
        pytest.param(date(1, 1, 1), "Waning Gibbous", 75.7, 19.61, id="year-1"),
        pytest.param(
            date(9999, 12, 31), "Waning Crescent", 1.5, 28.43, id="year-9999"
        ),
    ],
)
def test_moon_phase_matches_recorded_responses(day, name, illumination, age):
    assert moon.moon_phase(day) == MoonPhaseAtBirth(
        phase_name=name, illumination_percent=illumination, moon_age_days=age
    )


# Published full moons (UTC): 1993-03-08 09:46, 1996-08-28 17:52,
# 2024-04-23 23:49, 2024-05-23 13:53, 2025-01-13 22:27, 2025-02-12 13:53,
# 2025-04-13 00:22 and 2026-11-24 14:53.
@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        pytest.param(
            date(2025, 1, 14),
            date(2025, 2, 10),
            0,
            id="full-moon-90-min-before-birthday",
        ),
        pytest.param(
            date(2024, 12, 20),
            date(2025, 1, 13),
            1,
            id="full-moon-late-on-as-of",
        ),
        pytest.param(
            date(2025, 1, 13),
            date(2025, 2, 12),
            2,
            id="full-moon-on-both-end-days",
        ),
        pytest.param(
            date(2025, 1, 14),
            date(2025, 2, 11),
            0,
            id="as-of-the-day-before-a-full-moon",
        ),
        pytest.param(
            date(2025, 1, 13), date(2025, 1, 13), 1, id="single-full-moon-day"
        ),
        pytest.param(
            date(2025, 1, 14), date(2025, 1, 14), 0, id="single-day-without"
        ),
        pytest.param(
            date(2025, 3, 20),
            date(2025, 4, 12),
            0,
            id="full-moon-22-min-after-as-of",
        ),
        pytest.param(
            date(2025, 4, 13),
            date(2025, 4, 20),
            1,
            id="full-moon-22-min-after-birth-midnight",
        ),
        pytest.param(
            date(2024, 4, 1),
            date(2024, 4, 23),
            1,
            id="full-moon-11-min-before-as-of-ends",
        ),
        pytest.param(
            date(2024, 4, 24),
            date(2024, 5, 20),
            0,
            id="full-moon-11-min-before-birthday",
        ),
        pytest.param(
            date(1993, 3, 8), date(1996, 8, 28), 44, id="full-moon-each-end"
        ),
        pytest.param(
            date(1993, 3, 9), date(1996, 8, 27), 42, id="ends-just-missed"
        ),
    ],
)
def test_full_moons_counted_from_birth_midnight_to_end_of_as_of(
    birth, as_of, expected
):
    assert moon.count_full_moons(birth, as_of) == expected


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        pytest.param(date(2025, 2, 10), "2025-02-12", id="two-days-ahead"),
        pytest.param(date(2025, 1, 13), "2025-01-13", id="late-on-as-of"),
        pytest.param(date(2025, 1, 14), "2025-02-12", id="just-missed"),
        pytest.param(date(2025, 4, 12), "2025-04-13", id="22-min-after"),
        pytest.param(
            date(2025, 3, 20), "2025-04-13", id="22-min-after-a-month-on"
        ),
        pytest.param(date(2023, 12, 20), "2023-12-27", id="33-min-after"),
        pytest.param(date(2024, 4, 23), "2024-04-23", id="11-min-before-end"),
        pytest.param(
            date(2024, 3, 30), "2024-04-23", id="11-min-before-end-a-month-on"
        ),
        pytest.param(date(2024, 4, 24), "2024-05-23", id="11-min-before"),
        pytest.param(date(2026, 11, 18), "2026-11-24", id="2026"),
        pytest.param(date(1996, 8, 28), "1996-08-28", id="1996"),
    ],
)
def test_next_full_moon_gives_utc_date_of_published_full_moon(as_of, expected):
    assert moon.next_full_moon(as_of) == expected


@pytest.fixture
def full_moon_at_midnight(monkeypatch):
    """Puts a full moon exactly at midnight UTC on 1 March 2025."""
    # No real full moon falls exactly on a midnight, so a Moon moving at
    # its mean rate stands in for the ephemeris.
    instant = Time("2025-03-01", format="iso")

    def steady_lead(when):
        return (180 + (when - instant).jd * 360 / 29.530588853) % 360

    monkeypatch.setattr(moon, "_lead_deg", steady_lead)
    return date(2025, 3, 1)


@pytest.mark.parametrize("days_before", [0, 1], ids=["same-day", "day-before"])
def test_full_moon_exactly_at_midnight_is_dated_that_day(
    full_moon_at_midnight, days_before
):
    as_of = full_moon_at_midnight - timedelta(days=days_before)

    assert moon.next_full_moon(as_of) == "2025-03-01"


def test_full_moon_exactly_at_midnight_counts_from_that_birthday(
    full_moon_at_midnight,
):
    birth = full_moon_at_midnight

    assert moon.count_full_moons(birth, birth + timedelta(days=10)) == 1


def test_full_moon_exactly_at_midnight_is_not_in_the_day_before(
    full_moon_at_midnight,
):
    as_of = full_moon_at_midnight - timedelta(days=1)

    assert moon.count_full_moons(as_of - timedelta(days=10), as_of) == 0


def test_full_moons_from_year_1_to_9999_follow_the_mean_month():
    birth, as_of = date(1, 1, 1), date(9999, 12, 31)
    days = (as_of - birth).days + 1

    assert moon.count_full_moons(birth, as_of) == pytest.approx(
        days / 29.530589, abs=1
    )


@pytest.mark.parametrize(
    ("as_of", "pattern"),
    [
        pytest.param(date(1, 1, 1), r"0001-01-\d\d", id="year-1"),
        pytest.param(date(9999, 12, 31), r"10000-01-\d\d", id="year-9999"),
    ],
)
def test_next_full_moon_at_the_ends_of_the_calendar(as_of, pattern):
    assert re.fullmatch(pattern, moon.next_full_moon(as_of))


def test_add_moon_takes_phase_at_birth_and_counts_to_as_of():
    birth, as_of = date(1988, 3, 21), date(2026, 11, 18)
    result = FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )

    moon.add_moon(result, measure_lifetime(birth, as_of))

    assert (
        result.moon_phase_at_midnight_utc,
        result.full_moons_since_birth,
        result.next_full_moon_date,
    ) == (
        MoonPhaseAtBirth(
            phase_name="Waxing Crescent",
            illumination_percent=11.5,
            moon_age_days=3.23,
        ),
        478,
        "2026-11-24",
    )
