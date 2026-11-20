"""The Moon on the birthday, and full moons since.

Positions come from astropy's built-in analytical ephemeris (ERFA),
whose error is far below the rounding of the values returned. Every
quantity here but the lit share follows from the Moon's lead over the
Sun in ecliptic longitude: 0 degrees at new moon, 180 at full.
"""

import math
from datetime import date

import numpy as np
from astropy import units as u
from astropy.coordinates import GeocentricMeanEcliptic, get_body
from astropy.time import Time

from first_light.facts.age import Lifetime
from first_light.facts.dates import format_arrival_date
from first_light.facts.physics import SYNODIC_MONTH_DAYS
from first_light.models import FirstLightResponse, MoonPhaseAtBirth

# (moon age in days, phase name): a moon takes the name of the largest
# threshold at or below its age. The four principal phases get a day
# centred on their geometric instant, so a moon a few hours before
# exact full is "Full Moon" rather than "Waxing Gibbous"; the phases
# between fill the gaps, and the last half-day wraps to New Moon.
MOON_PHASES = (
    (0, "New Moon"),
    (0.5, "Waxing Crescent"),
    (6.8826, "First Quarter"),
    (7.8826, "Waxing Gibbous"),
    (14.2653, "Full Moon"),
    (15.2653, "Waning Gibbous"),
    (21.6479, "Third Quarter"),
    (22.6479, "Waning Crescent"),
    (29.0306, "New Moon"),
)

FULL_MOON_LEAD_DEG = 180
# Longer than any lunation, so the next full moon falls within this many
# days of any midnight.
LUNATION_SEARCH_DAYS = 31


def add_moon(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the moon category."""
    result.moon_phase_at_midnight_utc = moon_phase(life.birth)
    result.full_moons_since_birth = count_full_moons(life.birth, life.as_of)
    result.next_full_moon_date = next_full_moon(life.as_of)


def moon_phase(day: date) -> MoonPhaseAtBirth:
    """Works out the Moon's phase at midnight UTC on ``day``.

    The age is the lead scaled to a mean synodic month, so it is always
    half a month, 14.77 days, at full moon. Days since the true new moon
    can differ from it by up to about a day.
    """
    when = Time(day.isoformat(), format="iso")
    moon = get_body("moon", when)
    sun = get_body("sun", when)
    # The lit share of the disc follows from the phase angle, the angle
    # at the Moon between the Sun and the Earth. Taking that as 180
    # degrees less the elongation reads up to 0.14 points low.
    elongation = moon.separation(sun).rad
    sun_km = sun.distance.to_value(u.km)
    moon_km = moon.distance.to_value(u.km)
    phase_angle = math.atan2(
        sun_km * math.sin(elongation),
        moon_km - sun_km * math.cos(elongation),
    )
    illumination = (1 + math.cos(phase_angle)) / 2 * 100
    ecliptic = GeocentricMeanEcliptic(equinox=when)
    lead_deg = (
        moon.transform_to(ecliptic).lon - sun.transform_to(ecliptic).lon
    ).deg % 360
    age_days = lead_deg / 360 * SYNODIC_MONTH_DAYS
    name = next(
        phase
        for threshold, phase in reversed(MOON_PHASES)
        if age_days >= threshold
    )
    return MoonPhaseAtBirth(
        phase_name=name,
        illumination_percent=round(illumination, 1),
        moon_age_days=round(age_days, 2),
    )


def count_full_moons(birth: date, as_of: date) -> int:
    """Counts full moons from midnight UTC on ``birth`` to the end of ``as_of``.

    A full moon later in the day on ``as_of`` counts, as ``next_full_moon``
    gives that day.
    """
    start = Time(birth.isoformat(), format="iso")
    end = Time(as_of.isoformat(), format="iso") + 1 * u.day
    leads = _lead_deg(Time([start, end]))
    lead_start, lead_end = float(leads[0]), float(leads[1])
    elapsed_days: float = (end - start).jd
    # The lead tells the angle gained up to a whole number of turns, and
    # the mean rate tells the turns: the true lead strays from the mean by
    # about ten degrees, never close to half a turn.
    mean_gain = elapsed_days * 360 / SYNODIC_MONTH_DAYS
    change = (lead_end - lead_start) % 360
    gained = change + 360 * round((mean_gain - change) / 360)
    # A full moon is each time the lead passes 180 degrees.
    return math.ceil(
        (lead_start + gained - FULL_MOON_LEAD_DEG) / 360
    ) - math.ceil((lead_start - FULL_MOON_LEAD_DEG) / 360)


def next_full_moon(as_of: date) -> str:
    """Gives the UTC date of the first full moon from midnight on ``as_of``."""
    start = Time(as_of.isoformat(), format="iso")
    leads = _lead_deg(start + np.arange(LUNATION_SEARCH_DAYS + 1) * u.day)
    # Unwrapped, the lead gained since the first midnight only rises, so
    # the full moon falls in the day whose midnights bracket the target.
    gained = np.unwrap(leads - leads[0], period=360)
    target = (FULL_MOON_LEAD_DEG - leads[0]) % 360
    days_ahead = int(np.searchsorted(gained, target, side="right")) - 1
    return format_arrival_date(as_of, days_ahead)


def _lead_deg(when: Time) -> np.ndarray:
    """Gives the Moon's lead over the Sun in ecliptic longitude, 0 to 360."""
    ecliptic = GeocentricMeanEcliptic(equinox=when)
    moon = get_body("moon", when).transform_to(ecliptic)
    sun = get_body("sun", when).transform_to(ecliptic)
    lead: np.ndarray = (moon.lon - sun.lon).deg % 360
    return lead
