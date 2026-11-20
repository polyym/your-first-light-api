"""Links to pages about a birthday elsewhere."""

from datetime import date

from first_light.facts.age import Lifetime
from first_light.models import FirstLightResponse

APOD_BASE_URL = "https://apod.nasa.gov/apod/"
APOD_FRONT_PAGE = f"{APOD_BASE_URL}astropix.html"
APOD_FIRST_DAY = date(1995, 6, 16)
# Page names carry a two-digit year, so a later day would share its name
# with a picture from a hundred years before.
APOD_LAST_NAMEABLE_DAY = date(2095, 6, 15)


def add_links(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the links category."""
    result.nasa_apod_url = apod_url(life.birth)


def apod_url(day: date) -> str:
    """Links NASA's Astronomy Picture of the Day for ``day``.

    Returns:
        The day's page, or APOD's front page for a day before APOD began
        or too late for its page names.
    """
    if not APOD_FIRST_DAY <= day <= APOD_LAST_NAMEABLE_DAY:
        return APOD_FRONT_PAGE
    return f"{APOD_BASE_URL}ap{day.strftime('%y%m%d')}.html"
