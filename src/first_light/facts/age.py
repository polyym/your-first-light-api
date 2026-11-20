"""How long someone has been alive, measured once for every category."""

import math
from dataclasses import dataclass
from datetime import date

from astropy import units as u
from astropy.time import Time

from first_light.facts.dates import count_leap_days
from first_light.facts.physics import (
    DAYS_PER_JULIAN_YEAR,
    SIDEREAL_DAY_SECONDS,
)
from first_light.models import FirstLightResponse, PlanetaryAge

# astropy's elapsed seconds can fall a hair short of the whole number
# they should be (1553212820.9999998 for a lifetime of 1553212821 s),
# far less than this.
ELAPSED_SECONDS_SLACK = 0.001

# Orbital periods in Earth days.
PLANET_YEAR_DAYS = {
    "Mercury": 87.97,
    "Venus": 224.7,
    "Earth": DAYS_PER_JULIAN_YEAR,
    "Mars": 687.0,
    "Jupiter": 4_332.59,
    "Saturn": 10_755.70,
    "Uranus": 30_688.5,
    "Neptune": 60_195.0,
    "Pluto": 90_560.0,
}


@dataclass(frozen=True)
class Lifetime:
    """The time from midnight UTC on a birthday to midnight UTC on as_of.

    Attributes:
        birth: The birthday.
        as_of: The reference date.
        years: Elapsed Julian years. Light travels one light-year a
            year, so this is also the light sphere's radius.
        days: Whole calendar days.
        seconds: Elapsed SI seconds, leap seconds included.
    """

    birth: date
    as_of: date
    years: float
    days: int
    seconds: int

    @property
    def minutes(self) -> int:
        """Whole minutes elapsed."""
        return self.seconds // 60

    @property
    def hours(self) -> int:
        """Whole hours elapsed."""
        return self.seconds // 3600


def measure_lifetime(birth: date, as_of: date) -> Lifetime:
    """Measures the time from ``birth`` to ``as_of``.

    astropy subtracts UTC instants on the atomic time scale, so years
    and seconds are physical time and include every leap second in
    between. Days come from calendar arithmetic instead: a truncated
    physical day count would come up one short if a negative leap
    second were ever inserted.
    """
    elapsed = Time(as_of.isoformat(), format="iso") - Time(
        birth.isoformat(), format="iso"
    )
    return Lifetime(
        birth=birth,
        as_of=as_of,
        years=elapsed.to(u.yr).value,
        days=(as_of - birth).days,
        # Whole seconds completed. From 1972 midnight to midnight is a
        # whole number of seconds; before then UTC ran on fractional
        # offsets, and a part second left over is not counted.
        seconds=math.floor(elapsed.to(u.s).value + ELAPSED_SECONDS_SLACK),
    )


def add_time_alive(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the time_alive category."""
    result.age_years = round(life.years, 2)
    result.age_days = life.days
    result.age_hours = life.hours
    result.age_minutes = life.minutes
    result.age_seconds = life.seconds
    result.earth_rotations = round(life.seconds / SIDEREAL_DAY_SECONDS, 2)
    result.leap_years_lived_through = count_leap_days(life.birth, life.as_of)


def add_planetary_ages(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the planetary_ages category: age in each planet's years."""
    result.planetary_ages = [
        PlanetaryAge(
            planet=planet,
            age=round(life.days / year_days, 2),
            orbital_period_earth_days=year_days,
        )
        for planet, year_days in PLANET_YEAR_DAYS.items()
    ]
