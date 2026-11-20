"""Calendar arithmetic shared by several categories."""

import calendar
from datetime import date

# One Gregorian cycle: the calendar repeats every 400 years exactly.
_GREGORIAN_CYCLE_DAYS = 146_097
_GREGORIAN_CYCLE_YEARS = 400
_MAX_ORDINAL = date.max.toordinal()


def format_arrival_date(base: date, days_after: float) -> str:
    """Formats the calendar date a number of days after ``base``.

    Plain date arithmetic, about 75 times cheaper than an astropy
    ``Time`` per star, which matters for a list of 50,000 stars.

    Args:
        base: The starting date.
        days_after: A non-negative offset. A fraction of a day is
            dropped, as for any instant after midnight.

    Returns:
        ``YYYY-MM-DD``, with years below 1000 padded to four digits and
        years beyond 9999, which ``datetime.date`` cannot hold, written
        with five.
    """
    ordinal = base.toordinal() + int(days_after)
    if ordinal <= _MAX_ORDINAL:
        return date.fromordinal(ordinal).isoformat()
    # Shift back whole cycles into date's range, then add the years back.
    cycles = -(-(ordinal - _MAX_ORDINAL) // _GREGORIAN_CYCLE_DAYS)
    shifted = date.fromordinal(ordinal - cycles * _GREGORIAN_CYCLE_DAYS)
    year = shifted.year + cycles * _GREGORIAN_CYCLE_YEARS
    return f"{year}-{shifted.month:02d}-{shifted.day:02d}"


def count_leap_days(birth: date, as_of: date) -> int:
    """Counts the 29 Februaries from ``birth`` to ``as_of``, both included."""
    count = sum(
        1
        for year in {birth.year, as_of.year}
        if calendar.isleap(year) and birth <= date(year, 2, 29) <= as_of
    )
    first_full_year = birth.year + 1
    last_full_year = as_of.year - 1
    if first_full_year <= last_full_year:
        count += _leap_years_up_to(last_full_year) - _leap_years_up_to(
            first_full_year - 1
        )
    return count


def _leap_years_up_to(year: int) -> int:
    """Counts the leap years from year 1 to ``year``, both included."""
    return year // 4 - year // 100 + year // 400
