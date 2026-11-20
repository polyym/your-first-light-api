"""The stars a birthday's light has reached, and what orbits them."""

import re
from collections import Counter

from first_light.facts.age import Lifetime
from first_light.facts.catalogues import NEARBY_STARS, Star
from first_light.facts.dates import format_arrival_date
from first_light.facts.physics import DAYS_PER_JULIAN_YEAR
from first_light.models import (
    BirthdayStar,
    FirstLightResponse,
    NextStar,
    StarInfo,
)

# The faintest apparent magnitude the unaided eye sees on a dark night.
NAKED_EYE_MAG_LIMIT = 6.5
# How far a star's distance may be from someone's age for it to be
# their birthday star.
BIRTHDAY_STAR_TOLERANCE_LY = 2.0
# The share of known exoplanets that are rocky and in the conservative
# habitable zone, from Kepler's statistics.
HABITABLE_FRACTION = 0.07

SPECTRAL_CLASSES = {
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
}
# A subdwarf's type starts with a luminosity prefix, "sdM1" for one of
# class M. The label keeps the letter S that clients have long keyed on.
SUBDWARF_PREFIXES = ("sd", "esd", "usd")
# Luminosity class I, II or III, a supergiant, bright giant or giant, right
# after the temperature class, a range of them or a metallic-line class:
# "K1.5III", "M0 IIIe", "F0Ia", "K0/K1III", "M1-2Ia-Iab", "F2mF5IIp". A IV
# or V after the I is a subgiant or dwarf, and a colon after the
# temperature class marks the type uncertain, as in 36 Ophiuchi A's
# "K2:III:" (it is a K dwarf): both keep the dwarf label.
GIANT_TYPE = re.compile(
    r"[A-Z][0-9.]*(?:[/-][A-Z]?[0-9.]*)?(?:m[A-Z][0-9.]*)?\s*I{1,3}(?!V)"
)
GIANT_CLASSES = {
    "O": "Blue giant (O)",
    "B": "Blue giant (B)",
    "A": "White giant (A)",
    "F": "Yellow-white giant (F)",
    "G": "Yellow giant (G)",
    "K": "Orange giant (K)",
    "M": "Red giant (M)",
}
SUBDWARF_CLASS = "Subdwarf (S)"


def stars_reached(radius_ly: float) -> list[Star]:
    """Lists the catalogue stars within ``radius_ly``, nearest first."""
    return sorted(
        (star for star in NEARBY_STARS if star["distance_ly"] <= radius_ly),
        key=lambda star: star["distance_ly"],
    )


def add_stars(
    result: FirstLightResponse,
    life: Lifetime,
    reached: list[Star],
    star_limit: int,
) -> None:
    """Fills the stars category.

    Counts and the next star come from every star reached; only the
    first ``star_limit`` are built into the list, which is where the
    time goes.
    """
    radius_ly = life.years
    result.stars_reached = len(reached)
    result.naked_eye_stars_reached = sum(
        1 for star in reached if _is_naked_eye(star)
    )
    # The shell between last year's radius and this year's.
    year_ago_radius_ly = max(0.0, radius_ly - 1.0)
    result.stars_reached_this_year = sum(
        1 for star in reached if star["distance_ly"] > year_ago_radius_ly
    )
    result.birthday_star = find_birthday_star(radius_ly)
    result.stars = [_star_info(star, life) for star in reached[:star_limit]]
    remaining = len(reached) - star_limit
    if remaining > 0:
        result.stars_remaining = (
            f"Your light has reached {remaining} "
            f"more star{'s' if remaining != 1 else ''}, "
            f"with the furthest being {reached[-1]['name']}."
        )
    result.next_star = _next_star(life)


def add_exoplanets(result: FirstLightResponse, reached: list[Star]) -> None:
    """Fills the exoplanets category."""
    total = sum(star["known_exoplanets"] for star in reached)
    result.estimated_exoplanets = total
    result.potentially_habitable = round(total * HABITABLE_FRACTION)


def add_star_classification(
    result: FirstLightResponse, reached: list[Star]
) -> None:
    """Fills the star_classification category: stars reached by class."""
    result.star_type_breakdown = dict(
        Counter(classify_spectral(star["spectral_type"]) for star in reached)
    )


def classify_spectral(spectral_type: str) -> str:
    """Names the class of an MK spectral type, such as ``"G2V"``.

    The label always ends in the class letter in brackets, which clients
    read to pick a colour: "Unknown" for an empty type is the exception.
    """
    if not spectral_type:
        return "Unknown"
    if spectral_type.startswith(SUBDWARF_PREFIXES):
        return SUBDWARF_CLASS
    letter = spectral_type[0].upper()
    if letter in GIANT_CLASSES and GIANT_TYPE.match(spectral_type):
        return GIANT_CLASSES[letter]
    return SPECTRAL_CLASSES.get(letter, f"Other ({letter})")


def find_birthday_star(radius_ly: float) -> BirthdayStar | None:
    """Finds the star whose distance in light-years is nearest the age.

    The light seen from it today left it around the day of the birth.

    Returns:
        The star, or None when none is within
        ``BIRTHDAY_STAR_TOLERANCE_LY``.
    """
    best = min(
        NEARBY_STARS,
        key=lambda star: abs(star["distance_ly"] - radius_ly),
        default=None,
    )
    if best is None:
        return None
    difference = abs(best["distance_ly"] - radius_ly)
    if difference > BIRTHDAY_STAR_TOLERANCE_LY:
        return None
    return BirthdayStar(
        name=best["name"],
        distance_ly=round(best["distance_ly"], 2),
        spectral_type=best["spectral_type"],
        difference_ly=round(difference, 2),
    )


def _is_naked_eye(star: Star) -> bool:
    return star["apparent_magnitude"] <= NAKED_EYE_MAG_LIMIT


def _star_info(star: Star, life: Lifetime) -> StarInfo:
    return StarInfo(
        name=star["name"],
        distance_ly=round(star["distance_ly"], 2),
        spectral_type=star["spectral_type"],
        spectral_class=classify_spectral(star["spectral_type"]),
        apparent_magnitude=star["apparent_magnitude"],
        magnitude_band=star["magnitude_band"],
        known_exoplanets=star["known_exoplanets"],
        your_age_at_light_arrival_years=round(star["distance_ly"], 2),
        light_arrival_date=format_arrival_date(
            life.birth, star["distance_ly"] * DAYS_PER_JULIAN_YEAR
        ),
        naked_eye_visible=_is_naked_eye(star),
        ra_deg=star["ra_deg"],
        dec_deg=star["dec_deg"],
    )


def _next_star(life: Lifetime) -> NextStar | None:
    """Finds the nearest star the light has not reached yet."""
    upcoming = min(
        (star for star in NEARBY_STARS if star["distance_ly"] > life.years),
        key=lambda star: star["distance_ly"],
        default=None,
    )
    if upcoming is None:
        return None
    arrives_in_years = upcoming["distance_ly"] - life.years
    return NextStar(
        name=upcoming["name"],
        distance_ly=round(upcoming["distance_ly"], 2),
        arrives_in_years=round(arrives_in_years, 2),
        # Counted from the birthday, as light_arrival_date is: counted
        # from as_of, leap seconds or a float a hair short of a whole
        # day would give the day before.
        arrival_date=format_arrival_date(
            life.birth, upcoming["distance_ly"] * DAYS_PER_JULIAN_YEAR
        ),
    )
