"""Tests for the calendar arithmetic in first_light.facts.dates."""

from datetime import date

import pytest

from first_light.facts.dates import count_leap_days, format_arrival_date


@pytest.mark.parametrize(
    ("base", "days_after", "expected"),
    [
        pytest.param(date(1998, 11, 15), 0, "1998-11-15", id="same-day"),
        pytest.param(date(1998, 11, 15), 1, "1998-11-16", id="next-day"),
        pytest.param(
            date(1998, 11, 15), 0.99, "1998-11-15", id="fraction-dropped"
        ),
        pytest.param(date(2024, 2, 28), 1, "2024-02-29", id="into-leap-day"),
        pytest.param(date(9999, 12, 31), 0, "9999-12-31", id="last-date"),
    ],
)
def test_arrival_date_counts_whole_days_from_base(base, days_after, expected):
    assert format_arrival_date(base, days_after) == expected


@pytest.mark.parametrize(
    ("base", "days_after", "expected"),
    [
        pytest.param(date(1, 1, 1), 0, "0001-01-01", id="year-1"),
        pytest.param(date(999, 12, 31), 0, "0999-12-31", id="year-999"),
        pytest.param(date(999, 12, 31), 1, "1000-01-01", id="year-1000"),
    ],
)
def test_arrival_date_pads_early_years_to_four_digits(
    base, days_after, expected
):
    assert format_arrival_date(base, days_after) == expected


@pytest.mark.parametrize(
    ("days_after", "expected"),
    [
        pytest.param(1, "10000-01-01", id="one-past-9999"),
        pytest.param(60, "10000-02-29", id="leap-day-of-10000"),
        pytest.param(61, "10000-03-01", id="after-leap-day-of-10000"),
        pytest.param(367, "10001-01-01", id="after-leap-year-10000"),
        pytest.param(36_584, "10100-02-28", id="common-century-10100"),
        pytest.param(36_585, "10100-03-01", id="no-leap-day-in-10100"),
    ],
)
def test_arrival_date_beyond_9999_has_five_digit_year(days_after, expected):
    assert format_arrival_date(date(9999, 12, 31), days_after) == expected


def test_arrival_date_many_gregorian_cycles_ahead():
    hundred_cycles = 100 * 146_097
    assert (
        format_arrival_date(date(2000, 1, 1), hundred_cycles) == "42000-01-01"
    )


@pytest.mark.parametrize(
    ("birth", "as_of", "expected"),
    [
        pytest.param(date(2024, 1, 1), date(2024, 12, 31), 1, id="leap-year"),
        pytest.param(date(2023, 1, 1), date(2023, 12, 31), 0, id="common-year"),
        pytest.param(
            date(2024, 2, 29), date(2024, 2, 29), 1, id="single-day-29-feb"
        ),
        pytest.param(
            date(2023, 6, 1), date(2023, 6, 1), 0, id="single-common-day"
        ),
        pytest.param(
            date(2000, 2, 29), date(2000, 3, 1), 1, id="born-on-29-feb"
        ),
        pytest.param(
            date(2000, 2, 29), date(2004, 2, 29), 2, id="29-feb-to-29-feb"
        ),
        pytest.param(
            date(2024, 3, 1), date(2025, 12, 31), 0, id="born-after-29-feb"
        ),
        pytest.param(date(2020, 3, 1), date(2024, 2, 28), 0, id="as-of-28-feb"),
        pytest.param(date(2020, 3, 1), date(2024, 2, 29), 1, id="as-of-29-feb"),
        pytest.param(date(1899, 3, 1), date(1905, 1, 1), 1, id="spanning-1900"),
        pytest.param(date(1999, 3, 1), date(2001, 1, 1), 1, id="spanning-2000"),
        pytest.param(
            date(2003, 6, 1), date(2005, 1, 1), 1, id="leap-year-after-birth"
        ),
        pytest.param(
            date(2005, 6, 1), date(2009, 1, 1), 1, id="leap-year-before-as-of"
        ),
        pytest.param(date(1998, 11, 15), date(2026, 4, 11), 7, id="readme"),
        pytest.param(
            date(1, 1, 1), date(9999, 12, 31), 2424, id="years-1-to-9999"
        ),
    ],
)
def test_leap_days_counted_with_both_ends_included(birth, as_of, expected):
    assert count_leap_days(birth, as_of) == expected
