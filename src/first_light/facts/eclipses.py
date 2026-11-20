"""Eclipses in a lifetime, from NASA's catalogue of actual dates."""

import bisect
from datetime import date, timedelta

from first_light.facts.age import Lifetime
from first_light.facts.catalogues import (
    LUNAR_ECLIPSE_DATES,
    SOLAR_ECLIPSE_DATES,
)
from first_light.models import EclipseCounts, FirstLightResponse

# The span data/eclipses.json covers.
CATALOGUE_START = date(1900, 1, 1)
CATALOGUE_END = date(2100, 12, 31)


def add_eclipses(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the eclipses category."""
    result.eclipses = count_eclipses(life.birth, life.as_of)


def count_eclipses(birth: date, as_of: date) -> EclipseCounts:
    """Counts eclipses from ``birth`` to ``as_of``, both included.

    A lifetime that reaches outside the catalogue gets a note saying
    which part the counts cover. The next eclipses are left out when the
    catalogue cannot tell them: before it starts and after it ends.
    """
    solar, next_solar = _count_and_next(SOLAR_ECLIPSE_DATES, birth, as_of)
    lunar, next_lunar = _count_and_next(LUNAR_ECLIPSE_DATES, birth, as_of)
    # On the day before the catalogue starts its first eclipse is still
    # the next; any earlier, and an eclipse of 1899 may come before it.
    if as_of < CATALOGUE_START - timedelta(days=1):
        next_solar = next_lunar = None
    return EclipseCounts(
        solar_eclipses=solar,
        lunar_eclipses=lunar,
        total_eclipses=solar + lunar,
        next_solar_eclipse=next_solar,
        next_lunar_eclipse=next_lunar,
        coverage_note=_coverage_note(birth, as_of),
    )


def _coverage_note(birth: date, as_of: date) -> str | None:
    """Says which part of a lifetime the counts cover, when not all."""
    if CATALOGUE_START <= birth and as_of <= CATALOGUE_END:
        return None
    covers = f"Eclipse data covers {CATALOGUE_START.year}-{CATALOGUE_END.year}."
    covered_start = max(birth, CATALOGUE_START)
    covered_end = min(as_of, CATALOGUE_END)
    if covered_start > covered_end:
        return f"{covers} None of your lifetime falls within it."
    return (
        f"{covers} Counts reflect only the covered portion of your "
        f"lifetime ({covered_start.isoformat()} to "
        f"{covered_end.isoformat()})."
    )


def _count_and_next(
    dates: tuple[date, ...], birth: date, as_of: date
) -> tuple[int, str | None]:
    """Counts the sorted ``dates`` in range and finds the next after it."""
    first = bisect.bisect_left(dates, birth)
    # Also the index of the first date strictly after as_of.
    after = bisect.bisect_right(dates, as_of)
    upcoming = dates[after].isoformat() if after < len(dates) else None
    return after - first, upcoming
