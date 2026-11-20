"""Builds a response from the categories a caller asked for."""

from collections.abc import Set
from datetime import date

from first_light.facts.age import (
    add_planetary_ages,
    add_time_alive,
    measure_lifetime,
)
from first_light.facts.body import add_body_stats
from first_light.facts.eclipses import add_eclipses
from first_light.facts.links import add_links
from first_light.facts.moon import add_moon
from first_light.facts.scale import (
    add_cosmic_journey,
    add_light_sphere,
    add_scale_comparisons,
    add_universe_perspective,
)
from first_light.facts.stars import (
    add_exoplanets,
    add_star_classification,
    add_stars,
    stars_reached,
)
from first_light.facts.sun_sign import add_sun_constellation
from first_light.facts.voyagers import add_voyagers
from first_light.models import FirstLightResponse

# The categories that need nothing but the lifetime. The stars, exoplanets
# and star_classification categories share the list of stars reached, so
# they are filled apart.
_LIFETIME_CATEGORIES = {
    "time_alive": add_time_alive,
    "moon": add_moon,
    "light_sphere": add_light_sphere,
    "planetary_ages": add_planetary_ages,
    "body_stats": add_body_stats,
    "cosmic_journey": add_cosmic_journey,
    "scale_comparisons": add_scale_comparisons,
    "universe_perspective": add_universe_perspective,
    "sun_constellation": add_sun_constellation,
    "voyagers": add_voyagers,
    "eclipses": add_eclipses,
    "links": add_links,
}
_STAR_CATEGORIES = {"stars", "exoplanets", "star_classification"}


def compute_first_light(
    birth: date,
    as_of: date,
    categories: Set[str],
    star_limit: int,
) -> FirstLightResponse:
    """Computes the requested categories for a birthday.

    Args:
        birth: The birthday, before ``as_of``.
        as_of: The date to measure up to.
        categories: Names from ``models.Category``. The fields of any
            other category stay unset and are left out of the response.
        star_limit: The most stars to list. Counts and the next star
            always cover the whole catalogue.

    Returns:
        The response, with ``birthday`` and ``as_of`` always set.
    """
    life = measure_lifetime(birth, as_of)
    result = FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )
    for category, add in _LIFETIME_CATEGORIES.items():
        if category in categories:
            add(result, life)
    if categories & _STAR_CATEGORIES:
        reached = stars_reached(life.years)
        if "stars" in categories:
            add_stars(result, life, reached, star_limit)
        if "exoplanets" in categories:
            add_exoplanets(result, reached)
        if "star_classification" in categories:
            add_star_classification(result, reached)
    return result
