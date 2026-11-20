"""Tests for the link to NASA's Astronomy Picture of the Day."""

from datetime import date

import pytest

from first_light.facts.age import measure_lifetime
from first_light.facts.links import add_links, apod_url
from first_light.models import FirstLightResponse

FRONT_PAGE = "https://apod.nasa.gov/apod/astropix.html"


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        pytest.param(date(1995, 6, 15), FRONT_PAGE, id="day-before-first"),
        pytest.param(
            date(1995, 6, 16),
            "https://apod.nasa.gov/apod/ap950616.html",
            id="first-day",
        ),
        pytest.param(
            date(2000, 1, 1),
            "https://apod.nasa.gov/apod/ap000101.html",
            id="year-2000",
        ),
        pytest.param(
            date(2095, 6, 15),
            "https://apod.nasa.gov/apod/ap950615.html",
            id="last-nameable-day",
        ),
        pytest.param(date(2095, 6, 16), FRONT_PAGE, id="name-taken-by-1995"),
    ],
)
def test_apod_url_for_the_day_or_front_page(day, expected):
    assert apod_url(day) == expected


def test_add_links_uses_the_birthday():
    birth, as_of = date(1998, 11, 15), date(2026, 4, 11)
    result = FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )

    add_links(result, measure_lifetime(birth, as_of))

    assert result.nasa_apod_url == "https://apod.nasa.gov/apod/ap981115.html"
