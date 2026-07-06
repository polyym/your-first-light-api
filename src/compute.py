"""Astronomy computation engine for Your First Light.

Pure logic with no FastAPI dependency.  Takes dates in, returns
Pydantic models out.  All heavy astropy work is concentrated here
so the REST layer stays thin.

Typical usage from the app layer::

    from src.compute import compute_first_light
    result = compute_first_light(birth, ref, categories, star_limit)
"""

import bisect
import calendar
import json
import math
import warnings
from datetime import date
from pathlib import Path
from typing import Any

from astropy import units as u
from astropy.coordinates import (
    GeocentricMeanEcliptic,
    get_body,
    get_constellation,
)
from astropy.time import Time
from erfa import ErfaWarning

# Suppress ERFA "dubious year" warnings for pre-1960 dates.
# These are expected when users enter historical birthdays
# and do not affect calculation accuracy for our use case.
warnings.filterwarnings("ignore", category=ErfaWarning)

from src.constants import (  # noqa: E402, I001
    AU_KM,
    AVG_BLINKS_PER_MIN,
    AVG_BREATHS_PER_MIN,
    AVG_HEARTBEATS_PER_MIN,
    AMBIENT_TEMP_K,
    BIRTHDAY_STAR_TOLERANCE_LY,
    BODY_SURFACE_AREA_M2,
    BODY_TEMP_K,
    EARTH_ORBITAL_SPEED_KM_S,
    EARTH_VOLUME_KM3,
    GALACTIC_ORBITAL_PERIOD_MYR,
    GREAT_ATTRACTOR_SPEED_KM_S,
    HABITABLE_FRACTION,
    HOURS_PER_YEAR,
    HUBBLE_CONSTANT,
    LIGHT_SPEED_KM_S,
    LY_KM,
    MEAN_IR_PHOTON_ENERGY_J,
    MILKY_WAY_DIAMETER_LY,
    MOON_DISTANCE_KM,
    MOON_PHASES,
    MPC_KM,
    NAKED_EYE_MAG_LIMIT,
    NEW_MOON_JD,
    OBSERVABLE_UNIVERSE_DIAMETER_LY,
    PLANET_YEAR_DAYS,
    PLUTO_DISTANCE_KM,
    SECONDS_PER_YEAR,
    SIDEREAL_DAY_SECONDS,
    SIGN_CONSTELLATIONS,
    STEFAN_BOLTZMANN,
    SUN_DISTANCE_KM,
    SUN_GALACTIC_ORBITAL_SPEED_KM_S,
    SYNODIC_MONTH,
    UNIVERSE_AGE_YEARS,
    VOYAGER_1_LAUNCH,
    VOYAGER_1_MILESTONES,
    VOYAGER_1_SPEED_KM_S,
    VOYAGER_2_LAUNCH,
    VOYAGER_2_MILESTONES,
    VOYAGER_2_SPEED_KM_S,
    WAKING_FRACTION,
    ZODIAC_SIGNS,
)
from src.models import (  # noqa: E402
    BirthdayStar,
    BodyStats,
    CosmicJourney,
    EclipseCounts,
    FirstLightResponse,
    LightSphere,
    MoonPhaseAtBirth,
    NextStar,
    PlanetaryAge,
    ScaleComparison,
    StarInfo,
    SunConstellation,
    VoyagerStatus,
)

# -------------------------------------------------------------------
# Star catalogue (loaded once at import time)
# -------------------------------------------------------------------
_STARS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "stars.json"
)
with open(_STARS_PATH, encoding="utf-8") as _f:
    NEARBY_STARS: list[dict[str, Any]] = json.load(_f)

# -------------------------------------------------------------------
# Data manifest (optional; written by tools/update_data.py)
# -------------------------------------------------------------------
_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "manifest.json"
)
try:
    with open(_MANIFEST_PATH, encoding="utf-8") as _f:
        DATA_MANIFEST: dict[str, Any] = json.load(_f)
except (OSError, json.JSONDecodeError):
    DATA_MANIFEST = {}

# -------------------------------------------------------------------
# Eclipse catalogue (loaded once at import time)
# Source: NASA Five Millennium Catalog of Eclipses
# -------------------------------------------------------------------
_ECLIPSES_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "eclipses.json"
)
with open(_ECLIPSES_PATH, encoding="utf-8") as _f:
    _eclipse_data = json.load(_f)
    SOLAR_ECLIPSE_DATES: tuple[date, ...] = tuple(
        date.fromisoformat(d)
        for d in _eclipse_data["solarEclipses"]
    )
    LUNAR_ECLIPSE_DATES: tuple[date, ...] = tuple(
        date.fromisoformat(d)
        for d in _eclipse_data["lunarEclipses"]
    )


# -------------------------------------------------------------------
# Astro helpers
# -------------------------------------------------------------------
def classify_spectral(sp: str) -> str:
    """Map a spectral type string to a human-friendly label.

    Args:
        sp: Spectral type code (e.g. ``"G2V"``, ``"M5.5V"``).

    Returns:
        A readable classification like ``"Sun-like (G)"``.
    """
    if not sp:
        return "Unknown"
    ch = sp[0].upper()
    return {
        "O": "Blue giant (O)",
        "B": "Blue-white (B)",
        "A": "White (A)",
        "F": "Yellow-white (F)",
        "G": "Sun-like (G)",
        "K": "Orange dwarf (K)",
        "M": "Red dwarf (M)",
        "L": "Brown dwarf (L)",
        "T": "Brown dwarf (T)",
        "Y": "Sub-brown dwarf (Y)",
        "D": "White dwarf (D)",
    }.get(ch, f"Other ({ch})")


def compute_moon_phase(d: date) -> MoonPhaseAtBirth:
    """Compute the lunar phase at midnight UTC for a given date.

    Uses astropy's ``get_body()`` with its built-in analytical
    ephemeris (ERFA) to compute geocentric positions of the
    Moon and Sun, then derives phase from their ecliptic
    longitude difference.  ERFA's error is far below the
    rounding applied to the response values.

    Note: The phase is evaluated at midnight UTC (00:00) on the
    given date. Intra-day variation is not captured.

    Args:
        d: The date to evaluate.

    Returns:
        A ``MoonPhaseAtBirth`` with phase name, illumination,
        and moon age in days (all at midnight UTC).
    """
    t = Time(d.isoformat(), format="iso")

    moon = get_body("moon", t)
    sun = get_body("sun", t)

    # Illumination from angular separation
    elongation = moon.separation(sun)
    illumination = (1 - math.cos(elongation.rad)) / 2 * 100

    # Moon age from ecliptic longitude difference
    moon_ecl = moon.transform_to(
        GeocentricMeanEcliptic(equinox=t),
    )
    sun_ecl = sun.transform_to(
        GeocentricMeanEcliptic(equinox=t),
    )
    delta_lon = (moon_ecl.lon - sun_ecl.lon).deg % 360
    moon_age = delta_lon / 360 * SYNODIC_MONTH

    # Phase name from moon age
    phase_name = "New Moon"
    for threshold, name in reversed(MOON_PHASES):
        if moon_age >= threshold:
            phase_name = name
            break

    return MoonPhaseAtBirth(
        phase_name=phase_name,
        illumination_percent=round(illumination, 1),
        moon_age_days=round(moon_age, 2),
    )


def count_full_moons(birth: date, ref: date) -> int:
    """Count full moons between two dates.

    Both endpoint days are included: a full moon later in the
    day on *ref* counts, so the result is consistent with
    ``compute_moon_phase`` reporting "Full Moon" on that date.

    Args:
        birth: Start date (inclusive).
        ref: End date (inclusive, through end of day).

    Returns:
        Number of full moons that occurred in the interval.
    """
    t_birth = Time(birth.isoformat(), format="iso")
    t_ref = Time(ref.isoformat(), format="iso")
    birth_age = (t_birth.jd - NEW_MOON_JD) % SYNODIC_MONTH
    days_to_first = (14.765 - birth_age) % SYNODIC_MONTH
    first_full_jd = t_birth.jd + days_to_first
    # t_ref.jd is midnight UTC; extend to the end of the ref day
    # so full moons on that day are counted.
    end_jd = t_ref.jd + 1.0
    if first_full_jd >= end_jd:
        return 0
    return int((end_jd - first_full_jd) / SYNODIC_MONTH) + 1


def next_full_moon(ref: date) -> str:
    """Date of the first full moon on or after *ref*.

    Uses the same mean synodic model as ``count_full_moons``,
    anchored at midnight UTC of *ref*; the modelled instant can
    differ from the true instant by a few hours.

    Args:
        ref: Reference date.

    Returns:
        ISO ``YYYY-MM-DD`` date string.
    """
    t_ref = Time(ref.isoformat(), format="iso")
    ref_age = (t_ref.jd - NEW_MOON_JD) % SYNODIC_MONTH
    days_to = (14.765 - ref_age) % SYNODIC_MONTH
    return format_arrival_date(ref, days_to)


def zodiac_sign_for(d: date) -> str:
    """Tropical (astrological) zodiac sign for a calendar date.

    Args:
        d: The date to look up.

    Returns:
        Sign name, e.g. ``"Sagittarius"``.
    """
    for start_month, start_day, sign in reversed(ZODIAC_SIGNS):
        if (d.month, d.day) >= (start_month, start_day):
            return sign
    # Before 20 January: Capricorn wraps the year boundary.
    return ZODIAC_SIGNS[-1][2]


def compute_sun_constellation(d: date) -> SunConstellation:
    """Locate the Sun on the sky for a birthday.

    Compares the IAU constellation actually containing the Sun
    (at midnight UTC) with the traditional zodiac sign for the
    date. They usually differ: the signs were fixed about 2,000
    years ago and axial precession has since shifted the Sun's
    apparent path by roughly one constellation.

    Args:
        d: The date to evaluate.

    Returns:
        A ``SunConstellation`` with both answers and whether
        they agree.
    """
    t = Time(d.isoformat(), format="iso")
    sun = get_body("sun", t)
    constellation = str(get_constellation(sun))
    # astropy's constellation name table misspells Ophiuchus.
    if constellation == "Ophiucus":
        constellation = "Ophiuchus"
    sign = zodiac_sign_for(d)
    equivalent = SIGN_CONSTELLATIONS.get(sign, sign)
    return SunConstellation(
        constellation=constellation,
        zodiac_sign=sign,
        matches_zodiac_sign=(constellation == equivalent),
    )


# One Gregorian 400-year cycle: used to format arrival dates
# beyond year 9999, which ``datetime.date`` cannot represent.
_GREGORIAN_CYCLE_DAYS = 146_097
_MAX_ORDINAL = date.max.toordinal()


def format_arrival_date(base: date, days_after: float) -> str:
    """Format ``base + days_after`` as an ISO calendar date.

    Uses plain date arithmetic (roughly 75x cheaper than
    building an astropy ``Time`` per star) and produces
    well-formed dates for every reachable year: years below
    1000 are zero-padded to four digits, and years beyond 9999
    (which ``datetime.date`` cannot hold) are computed by
    shifting back whole 400-year Gregorian cycles.

    Args:
        base: Starting date.
        days_after: Non-negative day offset; fractions of a day
            are truncated, matching a midnight-based timestamp.

    Returns:
        An ISO ``YYYY-MM-DD`` string (five-digit year beyond
        year 9999).
    """
    ordinal = base.toordinal() + int(days_after)
    if ordinal <= _MAX_ORDINAL:
        return date.fromordinal(ordinal).isoformat()
    cycles = -(-(ordinal - _MAX_ORDINAL) // _GREGORIAN_CYCLE_DAYS)
    shifted = date.fromordinal(
        ordinal - cycles * _GREGORIAN_CYCLE_DAYS,
    )
    return (
        f"{shifted.year + cycles * 400}"
        f"-{shifted.month:02d}-{shifted.day:02d}"
    )


def find_birthday_star(
    radius_ly: float,
    all_stars: list[dict[str, Any]],
) -> BirthdayStar | None:
    """Find the star whose distance best matches the user's age.

    Args:
        radius_ly: The user's age in light-years (= light
            sphere radius).
        all_stars: Full star catalogue to search.

    Returns:
        A ``BirthdayStar`` if one is within the tolerance, or
        ``None`` if no star is close enough.
    """
    if not all_stars:
        return None
    best = min(
        all_stars,
        key=lambda s: abs(s["distance_ly"] - radius_ly),
    )
    diff = abs(best["distance_ly"] - radius_ly)
    if diff > BIRTHDAY_STAR_TOLERANCE_LY:
        return None
    return BirthdayStar(
        name=best["name"],
        distance_ly=round(best["distance_ly"], 2),
        spectral_type=best["spectral_type"],
        difference_ly=round(diff, 2),
    )


def make_apod_url(d: date) -> str:
    """Generate a NASA APOD URL for a given date.

    APOD started 1995-06-16; earlier dates fall back to the
    main APOD page.

    Args:
        d: The date to generate a URL for.

    Returns:
        A fully-qualified URL string.
    """
    apod_start = date(1995, 6, 16)
    if d < apod_start:
        return "https://apod.nasa.gov/apod/astropix.html"
    ymd = d.strftime("%y%m%d")
    return f"https://apod.nasa.gov/apod/ap{ymd}.html"


def _leap_years_through(y: int) -> int:
    """Count leap years from year 1 through year *y*.

    Args:
        y: The upper-bound year (inclusive).

    Returns:
        Number of leap years in the range ``[1, y]``.
    """
    if y <= 0:
        return 0
    return y // 4 - y // 100 + y // 400


def count_leap_years(birth: date, ref: date) -> int:
    """Count leap days between two dates.

    Uses an O(1) formula for the bulk of the range, with
    boundary checks for the first and last year.

    Args:
        birth: Start date (inclusive).
        ref: End date (inclusive).

    Returns:
        Number of Feb 29 occurrences in the interval.
    """
    count = 0

    # Boundary years: check if their Feb 29 falls in [birth, ref]
    for y in {birth.year, ref.year}:
        if calendar.isleap(y):
            if birth <= date(y, 2, 29) <= ref:
                count += 1

    # Full years strictly in between: every Feb 29 is in range
    lo = birth.year + 1
    hi = ref.year - 1
    if lo <= hi:
        count += (
            _leap_years_through(hi)
            - _leap_years_through(lo - 1)
        )

    return count


_ECLIPSE_START = date(1900, 1, 1)
_ECLIPSE_END = date(2100, 12, 31)


def count_eclipses(birth: date, ref: date) -> EclipseCounts:
    """Count solar and lunar eclipses between two dates.

    Uses the NASA Five Millennium Catalog of actual eclipse
    dates (1900–2100) with binary search.  When the requested
    range extends outside the catalogue window, a
    ``coverage_note`` is included in the result.

    Args:
        birth: Start date (inclusive).
        ref: End date (inclusive).

    Returns:
        An ``EclipseCounts`` with solar, lunar, totals, and an
        optional coverage note.
    """
    lo_s = bisect.bisect_left(SOLAR_ECLIPSE_DATES, birth)
    hi_s = bisect.bisect_right(SOLAR_ECLIPSE_DATES, ref)
    solar = hi_s - lo_s

    lo_l = bisect.bisect_left(LUNAR_ECLIPSE_DATES, birth)
    hi_l = bisect.bisect_right(LUNAR_ECLIPSE_DATES, ref)
    lunar = hi_l - lo_l

    # bisect_right already points at the first date strictly
    # after ref, which is exactly the next upcoming eclipse.
    next_solar = (
        SOLAR_ECLIPSE_DATES[hi_s].isoformat()
        if hi_s < len(SOLAR_ECLIPSE_DATES) else None
    )
    next_lunar = (
        LUNAR_ECLIPSE_DATES[hi_l].isoformat()
        if hi_l < len(LUNAR_ECLIPSE_DATES) else None
    )

    note = None
    if birth < _ECLIPSE_START or ref > _ECLIPSE_END:
        covered_start = max(birth, _ECLIPSE_START)
        covered_end = min(ref, _ECLIPSE_END)
        note = (
            f"Eclipse data covers 1900-2100. Counts "
            f"reflect only the covered portion of your "
            f"lifetime ({covered_start.isoformat()} to "
            f"{covered_end.isoformat()})."
        )

    return EclipseCounts(
        solar_eclipses=solar,
        lunar_eclipses=lunar,
        total_eclipses=solar + lunar,
        next_solar_eclipse=next_solar,
        next_lunar_eclipse=next_lunar,
        coverage_note=note,
    )


def _interpolate_distance(
    query: date,
    milestones: tuple[tuple[date, float], ...],
) -> float:
    """Linearly interpolate heliocentric distance from milestones.

    Args:
        query: The date to estimate distance for.
        milestones: Sorted ``(date, distance_au)`` pairs from
            JPL Horizons.

    Returns:
        Estimated heliocentric distance in AU.
    """
    if query <= milestones[0][0]:
        return milestones[0][1]
    if query >= milestones[-1][0]:
        # Extrapolate from last two points
        d1, au1 = milestones[-2]
        d2, au2 = milestones[-1]
        rate = (au2 - au1) / (d2 - d1).days
        extra_days = (query - d2).days
        return au2 + extra_days * rate

    for i in range(len(milestones) - 1):
        d1, au1 = milestones[i]
        d2, au2 = milestones[i + 1]
        if d1 <= query <= d2:
            frac = (query - d1).days / (d2 - d1).days
            return au1 + frac * (au2 - au1)

    return milestones[-1][1]  # fallback


def compute_voyager_status(
    birth: date,
    ref: date,
) -> list[VoyagerStatus]:
    """Calculate Voyager 1 and 2 distances since the user's birth.

    Uses piecewise-linear interpolation between known JPL
    Horizons distance milestones for accurate positions.

    Args:
        birth: User's date of birth.
        ref: Reference date (typically today).

    Returns:
        A list of two ``VoyagerStatus`` entries.
    """
    result: list[VoyagerStatus] = []
    probes = [
        (
            "Voyager 1", VOYAGER_1_LAUNCH,
            VOYAGER_1_SPEED_KM_S, VOYAGER_1_MILESTONES,
        ),
        (
            "Voyager 2", VOYAGER_2_LAUNCH,
            VOYAGER_2_SPEED_KM_S, VOYAGER_2_MILESTONES,
        ),
    ]
    for name, launch, speed, milestones in probes:
        launched_before = launch < birth
        dist_ref_au = _interpolate_distance(ref, milestones)
        dist_birth_au = _interpolate_distance(
            max(birth, launch), milestones,
        )
        delta_au = max(0.0, dist_ref_au - dist_birth_au)
        delta_km = delta_au * AU_KM
        result.append(VoyagerStatus(
            name=name,
            launch_date=launch.isoformat(),
            distance_travelled_since_birth_km=round(
                delta_km, 2,
            ),
            distance_travelled_since_birth_au=round(
                delta_au, 2,
            ),
            speed_km_s=speed,
            was_launched_before_birth=launched_before,
        ))
    return result


# -------------------------------------------------------------------
# Main computation orchestrator
# -------------------------------------------------------------------
def compute_first_light(
    birth: date,
    ref: date,
    cats: set[str],
    star_limit: int | None = None,
) -> FirstLightResponse:
    """Compute all requested categories for a birthday.

    Args:
        birth: User's date of birth.
        ref: Reference / "as of" date.
        cats: Set of category names to include.
        star_limit: Max stars to include in the stars list.
            ``None`` means return all. Counts and next_star
            are always computed from the full set.

    Returns:
        A fully-populated ``FirstLightResponse``.
    """
    t_birth = Time(birth.isoformat(), format="iso")
    t_ref = Time(ref.isoformat(), format="iso")
    delta = t_ref - t_birth
    age_years = delta.to(u.yr).value
    age_days = int(delta.to(u.day).value)
    age_seconds = int(delta.to(u.s).value)
    age_hours = int(age_seconds / 3600)
    age_minutes = int(age_seconds / 60)

    # Light sphere radius — cheap, needed by several categories
    radius_ly = age_years
    radius_km = (radius_ly * u.lyr).to(u.km).value

    result = FirstLightResponse(
        birthday=birth.isoformat(),
        as_of=ref.isoformat(),
    )

    # Pre-compute values shared across multiple categories
    volume_ly3 = (4 / 3) * math.pi * radius_ly**3
    galactic_km = (
        SUN_GALACTIC_ORBITAL_SPEED_KM_S * age_seconds
    )

    if "time_alive" in cats:
        result.age_years = round(age_years, 2)
        result.age_days = age_days
        result.age_hours = age_hours
        result.age_minutes = age_minutes
        result.age_seconds = age_seconds
        result.earth_rotations = round(
            age_seconds / SIDEREAL_DAY_SECONDS, 2,
        )
        result.leap_years_lived_through = count_leap_years(
            birth, ref,
        )

    if "moon" in cats:
        result.moon_phase_at_midnight_utc = compute_moon_phase(
            birth,
        )
        result.full_moons_since_birth = count_full_moons(
            birth, ref,
        )
        result.next_full_moon_date = next_full_moon(ref)

    if "light_sphere" in cats:
        radius_au = (radius_ly * u.lyr).to(u.AU).value
        surface_area = 4 * math.pi * radius_ly**2
        diameter = radius_ly * 2
        result.light_sphere = LightSphere(
            radius_ly=round(radius_ly, 2),
            diameter_ly=round(diameter, 2),
            radius_km=round(radius_km, 2),
            radius_au=round(radius_au, 2),
            volume_cubic_ly=round(volume_ly3, 2),
            surface_area_sq_ly=round(surface_area, 2),
            milky_way_diameter_percent=round(
                (diameter / MILKY_WAY_DIAMETER_LY) * 100, 6,
            ),
            observable_universe_diameter_percent=round(
                (diameter / OBSERVABLE_UNIVERSE_DIAMETER_LY)
                * 100,
                12,
            ),
        )
        result.speed_of_light_km_s = LIGHT_SPEED_KM_S

    # Stars, exoplanets, and classification share filtering
    need_stars = cats & {
        "stars", "exoplanets", "star_classification",
    }
    if need_stars:
        all_stars = NEARBY_STARS
        reached = sorted(
            [s for s in all_stars
             if s["distance_ly"] <= radius_ly],
            key=lambda s: s["distance_ly"],
        )

        if "stars" in cats:
            # Counts come from the full reached set; the
            # expensive per-star models are only built for the
            # slice that will actually be returned.
            naked_eye_count = sum(
                1 for s in reached
                if s["apparent_magnitude"] <= NAKED_EYE_MAG_LIMIT
            )
            truncated = (
                star_limit is not None
                and len(reached) > star_limit
            )
            returned = (
                reached[:star_limit] if truncated else reached
            )
            stars = [
                StarInfo(
                    name=s["name"],
                    distance_ly=round(s["distance_ly"], 2),
                    spectral_type=s["spectral_type"],
                    spectral_class=classify_spectral(
                        s["spectral_type"],
                    ),
                    apparent_magnitude=s["apparent_magnitude"],
                    magnitude_band=s.get("magnitude_band"),
                    known_exoplanets=s["known_exoplanets"],
                    your_age_at_light_arrival_years=round(
                        s["distance_ly"], 2,
                    ),
                    light_arrival_date=format_arrival_date(
                        birth, s["distance_ly"] * 365.25,
                    ),
                    naked_eye_visible=(
                        s["apparent_magnitude"]
                        <= NAKED_EYE_MAG_LIMIT
                    ),
                    ra_deg=s.get("ra_deg"),
                    dec_deg=s.get("dec_deg"),
                )
                for s in returned
            ]

            next_star = None
            ns = min(
                (s for s in all_stars
                 if s["distance_ly"] > radius_ly),
                key=lambda s: s["distance_ly"],
                default=None,
            )
            if ns is not None:
                arrives_in = ns["distance_ly"] - radius_ly
                next_star = NextStar(
                    name=ns["name"],
                    distance_ly=round(ns["distance_ly"], 2),
                    arrives_in_years=round(arrives_in, 2),
                    arrival_date=format_arrival_date(
                        ref, arrives_in * 365.25,
                    ),
                )

            result.stars_reached = len(reached)
            result.naked_eye_stars_reached = naked_eye_count
            # Stars first reached in the final year up to ref:
            # the shell between last year's radius and today's.
            year_ago_radius = max(0.0, radius_ly - 1.0)
            result.stars_reached_this_year = sum(
                1 for s in reached
                if s["distance_ly"] > year_ago_radius
            )
            result.birthday_star = find_birthday_star(
                radius_ly, all_stars,
            )
            result.stars = stars
            if star_limit is not None and truncated:
                remaining = len(reached) - star_limit
                furthest = reached[-1]["name"]
                result.stars_remaining = (
                    f"Your light has reached {remaining} "
                    f"more star{'s' if remaining != 1 else ''}"
                    f", with the furthest being {furthest}."
                )
            result.next_star = next_star

        if "exoplanets" in cats:
            total = sum(
                s["known_exoplanets"] for s in reached
            )
            habitable = (
                round(total * HABITABLE_FRACTION)
                if total > 0
                else 0
            )
            result.estimated_exoplanets = total
            result.potentially_habitable = habitable

        if "star_classification" in cats:
            type_counts: dict[str, int] = {}
            for s in reached:
                cls = classify_spectral(s["spectral_type"])
                type_counts[cls] = (
                    type_counts.get(cls, 0) + 1
                )
            result.star_type_breakdown = type_counts

    if "planetary_ages" in cats:
        result.planetary_ages = [
            PlanetaryAge(
                planet=p,
                age=round(age_days / d, 2),
                orbital_period_earth_days=d,
            )
            for p, d in PLANET_YEAR_DAYS.items()
        ]

    if "body_stats" in cats:
        gross = (
            STEFAN_BOLTZMANN
            * BODY_SURFACE_AREA_M2
            * BODY_TEMP_K**4
        )
        ambient = (
            STEFAN_BOLTZMANN
            * BODY_SURFACE_AREA_M2
            * AMBIENT_TEMP_K**4
        )
        net_thermal = gross - ambient
        total_photons = (
            (gross / MEAN_IR_PHOTON_ENERGY_J) * age_seconds
        )
        result.body_stats = BodyStats(
            estimated_heartbeats=int(
                AVG_HEARTBEATS_PER_MIN * age_minutes,
            ),
            estimated_breaths=int(
                AVG_BREATHS_PER_MIN * age_minutes,
            ),
            estimated_blinks=int(
                AVG_BLINKS_PER_MIN
                * (age_minutes * WAKING_FRACTION),
            ),
            photons_emitted=total_photons,
            thermal_power_watts=round(net_thermal, 2),
        )

    if "cosmic_journey" in cats:
        earth_km = EARTH_ORBITAL_SPEED_KM_S * age_seconds
        galactic_deg = (
            (age_years / (GALACTIC_ORBITAL_PERIOD_MYR * 1e6))
            * 360
        )
        expansion_pct = (
            ((HUBBLE_CONSTANT * age_seconds) / MPC_KM) * 100
        )
        attractor_km = (
            GREAT_ATTRACTOR_SPEED_KM_S * age_seconds
        )
        result.cosmic_journey = CosmicJourney(
            earth_distance_around_sun_km=round(earth_km, 2),
            earth_orbits_completed=round(age_years, 2),
            galactic_distance_km=round(galactic_km, 2),
            galactic_orbit_degrees=round(galactic_deg, 6),
            great_attractor_distance_km=round(
                attractor_km, 2,
            ),
            universe_expansion_percent=round(
                expansion_pct, 10,
            ),
        )

    if "scale_comparisons" in cats:
        diameter_km = radius_km * 2
        result.scale_comparisons = [
            ScaleComparison(
                label="Trips to the Moon",
                value=round(radius_km / MOON_DISTANCE_KM, 2),
                unit="trips",
            ),
            ScaleComparison(
                label="Trips to the Sun",
                value=round(radius_km / SUN_DISTANCE_KM, 2),
                unit="trips",
            ),
            ScaleComparison(
                label="Trips to Pluto",
                value=round(
                    radius_km / PLUTO_DISTANCE_KM, 2,
                ),
                unit="trips",
            ),
            ScaleComparison(
                label=(
                    "Time to cross your light sphere "
                    "by car at 100 km/h"
                ),
                value=round(
                    diameter_km / 100 / HOURS_PER_YEAR, 2,
                ),
                unit="years",
            ),
            ScaleComparison(
                label=(
                    "Time to cross by commercial jet "
                    "at 900 km/h"
                ),
                value=round(
                    diameter_km / 900 / HOURS_PER_YEAR, 2,
                ),
                unit="years",
            ),
            ScaleComparison(
                label=(
                    "Time to cross at Voyager 1 speed "
                    "(17 km/s)"
                ),
                value=round(
                    diameter_km / 17 / SECONDS_PER_YEAR, 2,
                ),
                unit="years",
            ),
            ScaleComparison(
                label=(
                    "Earths that could fit inside your "
                    "light sphere by volume"
                ),
                value=round(
                    volume_ly3 * LY_KM**3 / EARTH_VOLUME_KM3, 2,
                ),
                unit="earths",
            ),
            ScaleComparison(
                label=(
                    "Distance travelled through space "
                    "via galactic orbit"
                ),
                value=round(galactic_km, 2),
                unit="km",
            ),
        ]

    if "universe_perspective" in cats:
        result.universe_age_percent = round(
            (age_years / UNIVERSE_AGE_YEARS) * 100, 15,
        )

    if "sun_constellation" in cats:
        result.sun_constellation = compute_sun_constellation(
            birth,
        )

    if "voyagers" in cats:
        result.voyagers = compute_voyager_status(birth, ref)

    if "eclipses" in cats:
        result.eclipses = count_eclipses(birth, ref)

    if "links" in cats:
        result.nasa_apod_url = make_apod_url(birth)

    return result
