"""Tests for the star sign and the constellation the Sun was really in."""

from datetime import date

import pytest

from first_light.facts.age import measure_lifetime
from first_light.facts.sun_sign import (
    add_sun_constellation,
    sun_constellation,
    zodiac_sign,
)
from first_light.models import FirstLightResponse, SunConstellation


@pytest.mark.parametrize(
    ("month", "day", "sign"),
    [
        pytest.param(1, 1, "Capricorn", id="new-year"),
        pytest.param(1, 19, "Capricorn", id="before-aquarius"),
        pytest.param(1, 20, "Aquarius", id="aquarius"),
        pytest.param(2, 18, "Aquarius", id="before-pisces"),
        pytest.param(2, 19, "Pisces", id="pisces"),
        pytest.param(3, 20, "Pisces", id="before-aries"),
        pytest.param(3, 21, "Aries", id="aries"),
        pytest.param(4, 19, "Aries", id="before-taurus"),
        pytest.param(4, 20, "Taurus", id="taurus"),
        pytest.param(5, 20, "Taurus", id="before-gemini"),
        pytest.param(5, 21, "Gemini", id="gemini"),
        pytest.param(6, 20, "Gemini", id="before-cancer"),
        pytest.param(6, 21, "Cancer", id="cancer"),
        pytest.param(7, 22, "Cancer", id="before-leo"),
        pytest.param(7, 23, "Leo", id="leo"),
        pytest.param(8, 22, "Leo", id="before-virgo"),
        pytest.param(8, 23, "Virgo", id="virgo"),
        pytest.param(9, 22, "Virgo", id="before-libra"),
        pytest.param(9, 23, "Libra", id="libra"),
        pytest.param(10, 22, "Libra", id="before-scorpio"),
        pytest.param(10, 23, "Scorpio", id="scorpio"),
        pytest.param(11, 21, "Scorpio", id="before-sagittarius"),
        pytest.param(11, 22, "Sagittarius", id="sagittarius"),
        pytest.param(12, 21, "Sagittarius", id="before-capricorn"),
        pytest.param(12, 22, "Capricorn", id="capricorn"),
        pytest.param(12, 31, "Capricorn", id="new-years-eve"),
    ],
)
def test_sign_starts_on_its_newspaper_date(month, day, sign):
    assert zodiac_sign(date(2001, month, day)) == sign


@pytest.mark.parametrize(
    ("day", "constellation", "sign"),
    [
        pytest.param(date(1900, 1, 19), "Capricornus", "Capricorn", id="1900"),
        pytest.param(date(1000, 11, 10), "Scorpius", "Scorpio", id="1000"),
    ],
)
def test_sign_matches_constellation_through_iau_spelling(
    day, constellation, sign
):
    assert sun_constellation(day) == SunConstellation(
        constellation=constellation, zodiac_sign=sign, matches_zodiac_sign=True
    )


def test_sign_matches_constellation_of_the_same_name():
    assert sun_constellation(date(2000, 12, 20)) == SunConstellation(
        constellation="Sagittarius",
        zodiac_sign="Sagittarius",
        matches_zodiac_sign=True,
    )


def test_sign_differs_from_constellation_after_precession():
    assert sun_constellation(date(1998, 11, 15)) == SunConstellation(
        constellation="Libra", zodiac_sign="Scorpio", matches_zodiac_sign=False
    )


def test_ophiuchus_spelt_in_full():
    assert sun_constellation(date(2000, 12, 5)) == SunConstellation(
        constellation="Ophiuchus",
        zodiac_sign="Sagittarius",
        matches_zodiac_sign=False,
    )


def test_constellation_taken_at_midnight_not_later_in_the_day():
    # The Sun crosses from Taurus into Gemini at about 11:00 UTC that day.
    assert sun_constellation(date(2001, 6, 21)).constellation == "Taurus"


def test_add_sun_constellation_uses_the_birthday():
    birth, as_of = date(1988, 3, 21), date(2026, 11, 18)
    result = FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )

    add_sun_constellation(result, measure_lifetime(birth, as_of))

    assert result.sun_constellation == SunConstellation(
        constellation="Pisces", zodiac_sign="Aries", matches_zodiac_sign=False
    )
