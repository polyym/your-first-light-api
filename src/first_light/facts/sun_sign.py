"""Where the Sun really was on a birthday, against the star sign."""

from datetime import date

from astropy.coordinates import get_body, get_constellation
from astropy.time import Time

from first_light.facts.age import Lifetime
from first_light.models import FirstLightResponse, SunConstellation

# (start month, start day, sign): the conventional newspaper dates.
# A sign runs to the day before the next one starts; Capricorn wraps
# the end of the year.
ZODIAC_SIGNS = (
    (1, 20, "Aquarius"),
    (2, 19, "Pisces"),
    (3, 21, "Aries"),
    (4, 20, "Taurus"),
    (5, 21, "Gemini"),
    (6, 21, "Cancer"),
    (7, 23, "Leo"),
    (8, 23, "Virgo"),
    (9, 23, "Libra"),
    (10, 23, "Scorpio"),
    (11, 22, "Sagittarius"),
    (12, 22, "Capricorn"),
)

# Signs whose IAU constellation is spelt differently.
SIGN_CONSTELLATIONS = {
    "Scorpio": "Scorpius",
    "Capricorn": "Capricornus",
}


def add_sun_constellation(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the sun_constellation category."""
    result.sun_constellation = sun_constellation(life.birth)


def sun_constellation(day: date) -> SunConstellation:
    """Compares the Sun's constellation at midnight UTC with the sign.

    They usually differ: the signs were fixed about 2,000 years ago,
    and precession has since moved the Sun's path by about one
    constellation.
    """
    sun = get_body("sun", Time(day.isoformat(), format="iso"))
    constellation = str(get_constellation(sun))
    # astropy's constellation table misspells Ophiuchus.
    if constellation == "Ophiucus":
        constellation = "Ophiuchus"
    sign = zodiac_sign(day)
    return SunConstellation(
        constellation=constellation,
        zodiac_sign=sign,
        matches_zodiac_sign=(
            constellation == SIGN_CONSTELLATIONS.get(sign, sign)
        ),
    )


def zodiac_sign(day: date) -> str:
    """Gives the tropical star sign for a calendar date."""
    for start_month, start_day, sign in reversed(ZODIAC_SIGNS):
        if (day.month, day.day) >= (start_month, start_day):
            return sign
    # Before 20 January: still Capricorn from the previous December.
    return ZODIAC_SIGNS[-1][2]
