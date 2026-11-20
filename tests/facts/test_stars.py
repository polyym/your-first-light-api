"""Tests for the stars reached, their planets and their classes."""

from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from first_light.facts import stars
from first_light.facts.age import Lifetime, measure_lifetime
from first_light.facts.catalogues import NEARBY_STARS as SHIPPED_STARS
from first_light.models import FirstLightResponse

# Exactly ten Julian years; only years, birth and as_of are read.
TEN_YEARS = Lifetime(
    birth=date(2000, 1, 1),
    as_of=date(2010, 1, 1),
    years=10.0,
    days=3653,
    seconds=315_576_000,
)


def _star(
    name: str,
    distance_ly: float,
    spectral_type: str,
    magnitude: float,
    band: str | None,
    exoplanets: int,
    ra_deg: float,
    dec_deg: float,
) -> dict[str, Any]:
    return {
        "name": name,
        "distance_ly": distance_ly,
        "spectral_type": spectral_type,
        "apparent_magnitude": magnitude,
        "magnitude_band": band,
        "known_exoplanets": exoplanets,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
    }


# Out of distance order, so that sorting shows.
CATALOGUE = [
    _star("Far Away", 30.0, "F5V", 4.0, "V", 5, 10.0, 20.0),
    _star("Odd Letter", 10.0, "X9", 12.0, "G", 0, 30.0, 40.0),
    _star("Near Red", 1.504, "M5.5Ve", 11.13, "V", 3, 217.4289, -62.6795),
    _star("Next Door", 11.5, "M3V", 0.5, "V", 2, 50.0, 60.0),
    _star("Edge Faint", 7.0, "m4.5V", 6.51, "G", 10, 70.0, 80.0),
    _star("Unclassified", 9.5, "", 14.0, None, 4, 90.0, -10.0),
    _star("Bright Sun", 3.0, "G2V", -0.01, "V", 0, 110.0, -20.0),
    _star("Subdwarf", 9.0, "sdM1", 8.85, "V", 0, 77.9, -45.0),
    _star("Edge Bright", 5.0, "A1V", 6.5, "V", 0, 130.0, -30.0),
]
REACHED_IN_TEN_YEARS = [
    "Near Red",
    "Bright Sun",
    "Edge Bright",
    "Edge Faint",
    "Subdwarf",
    "Unclassified",
    "Odd Letter",
]
# Its published distance, which responses give as 4.25 and would be 4.2
# at one decimal.
PROXIMA_CENTAURI = _star(
    "Proxima Centauri", 4.2465, "M5.5Ve", 11.13, "V", 3, 217.4289, -62.6795
)


@pytest.fixture(autouse=True)
def catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts the synthetic catalogue in place of the shipped one."""
    monkeypatch.setattr(stars, "NEARBY_STARS", CATALOGUE)


def _with_stars(
    star_limit: int = 50, life: Lifetime = TEN_YEARS
) -> FirstLightResponse:
    result = FirstLightResponse(
        birthday=life.birth.isoformat(), as_of=life.as_of.isoformat()
    )
    stars.add_stars(result, life, stars.stars_reached(life.years), star_limit)
    return result


def test_stars_reached_are_those_within_the_radius_nearest_first() -> None:
    names = [star["name"] for star in stars.stars_reached(10.0)]

    assert names == REACHED_IN_TEN_YEARS


def test_stars_reached_counts_stars_left_out_of_the_list() -> None:
    assert _with_stars(star_limit=1).stars_reached == 7


def test_naked_eye_count_includes_magnitude_6_5_but_not_6_51() -> None:
    assert _with_stars().naked_eye_stars_reached == 2


def test_naked_eye_flag_marks_each_star_up_to_magnitude_6_5() -> None:
    listed = _with_stars().stars
    assert listed is not None

    assert {star.name: star.naked_eye_visible for star in listed} == {
        "Near Red": False,
        "Bright Sun": True,
        "Edge Bright": True,
        "Edge Faint": False,
        "Subdwarf": False,
        "Unclassified": False,
        "Odd Letter": False,
    }


def test_stars_reached_this_year_leaves_out_a_star_one_year_inside() -> None:
    assert _with_stars().stars_reached_this_year == 2


def test_star_info_carries_the_catalogue_entry() -> None:
    listed = _with_stars().stars
    assert listed is not None

    assert listed[0].model_dump() == {
        "name": "Near Red",
        "distance_ly": 1.5,
        "spectral_type": "M5.5Ve",
        "spectral_class": "Red dwarf (M)",
        "apparent_magnitude": 11.13,
        "magnitude_band": "V",
        "known_exoplanets": 3,
        "your_age_at_light_arrival_years": 1.5,
        "light_arrival_date": "2001-07-03",
        "naked_eye_visible": False,
        "ra_deg": 217.4289,
        "dec_deg": -62.6795,
    }


@pytest.mark.parametrize(
    "field",
    ["distance_ly", "your_age_at_light_arrival_years"],
    ids=["distance", "age-at-arrival"],
)
def test_star_info_gives_the_distance_to_two_decimals(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    monkeypatch.setattr(stars, "NEARBY_STARS", [PROXIMA_CENTAURI])

    listed = _with_stars().stars
    assert listed is not None

    assert getattr(listed[0], field) == 4.25


def test_light_arrival_date_counts_julian_years_from_birth() -> None:
    listed = _with_stars().stars
    assert listed is not None

    assert [(star.name, star.light_arrival_date) for star in listed] == [
        ("Near Red", "2001-07-03"),
        ("Bright Sun", "2002-12-31"),
        ("Edge Bright", "2004-12-31"),
        ("Edge Faint", "2006-12-31"),
        ("Subdwarf", "2008-12-31"),
        ("Unclassified", "2009-07-01"),
        ("Odd Letter", "2009-12-31"),
    ]


def test_list_stops_at_star_limit_keeping_the_nearest() -> None:
    listed = _with_stars(star_limit=3).stars
    assert listed is not None

    assert [star.name for star in listed] == [
        "Near Red",
        "Bright Sun",
        "Edge Bright",
    ]


@pytest.mark.parametrize(
    ("star_limit", "expected"),
    [
        pytest.param(
            3,
            "Your light has reached 4 more stars, with the furthest being "
            "Odd Letter.",
            id="plural",
        ),
        pytest.param(
            6,
            "Your light has reached 1 more star, with the furthest being "
            "Odd Letter.",
            id="singular",
        ),
        pytest.param(7, None, id="limit-equals-count"),
        pytest.param(8, None, id="limit-above-count"),
    ],
)
def test_stars_remaining_says_how_many_were_left_out(
    star_limit: int, expected: str | None
) -> None:
    assert _with_stars(star_limit=star_limit).stars_remaining == expected


def test_next_star_is_the_nearest_unreached_counted_from_as_of() -> None:
    next_star = _with_stars().next_star
    assert next_star is not None

    assert next_star.model_dump() == {
        "name": "Next Door",
        "distance_ly": 11.5,
        "arrives_in_years": 1.5,
        "arrival_date": "2011-07-02",
    }


def test_next_star_arrives_on_the_date_it_is_later_listed_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 84 light-years is a whole number of days, and the leap seconds make
    # this lifetime a hair longer than its whole days.
    monkeypatch.setattr(
        stars,
        "NEARBY_STARS",
        [_star("Whole Days", 84.0, "M3V", 9.0, "V", 0, 50.0, 60.0)],
    )
    birth = date(1942, 11, 20)
    day_before = measure_lifetime(birth, date(2026, 11, 19))
    day_after = measure_lifetime(birth, date(2026, 11, 21))

    next_star = _with_stars(life=day_before).next_star
    listed = _with_stars(life=day_after).stars
    assert next_star is not None
    assert listed is not None

    assert (
        next_star.arrival_date == listed[0].light_arrival_date == "2026-11-20"
    )


def test_next_star_arrival_is_given_to_two_decimals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        stars,
        "NEARBY_STARS",
        [_star("Next Up", 11.56, "M3V", 9.0, "V", 0, 50.0, 60.0)],
    )

    next_star = _with_stars().next_star
    assert next_star is not None

    assert next_star.arrives_in_years == 1.56


def test_next_star_left_out_once_the_furthest_star_is_reached() -> None:
    assert _with_stars(life=replace(TEN_YEARS, years=30.0)).next_star is None


def test_birthday_star_is_chosen_from_the_age() -> None:
    birthday_star = _with_stars().birthday_star
    assert birthday_star is not None

    assert birthday_star.model_dump() == {
        "name": "Odd Letter",
        "distance_ly": 10.0,
        "spectral_type": "X9",
        "difference_ly": 0.0,
    }


def test_birthday_star_is_the_closest_match_even_if_not_yet_reached() -> None:
    birthday_star = stars.find_birthday_star(11.0)
    assert birthday_star is not None

    assert birthday_star.model_dump() == {
        "name": "Next Door",
        "distance_ly": 11.5,
        "spectral_type": "M3V",
        "difference_ly": 0.5,
    }


def test_birthday_star_difference_is_given_to_two_decimals() -> None:
    birthday_star = stars.find_birthday_star(11.37)
    assert birthday_star is not None

    assert (birthday_star.name, birthday_star.difference_ly) == (
        "Next Door",
        0.13,
    )


@pytest.mark.parametrize(
    ("radius_ly", "expected_difference"),
    [
        pytest.param(13.5, 2.0, id="at-tolerance"),
        pytest.param(13.51, None, id="just-past-tolerance"),
    ],
)
def test_birthday_star_must_be_within_two_light_years(
    radius_ly: float, expected_difference: float | None
) -> None:
    birthday_star = stars.find_birthday_star(radius_ly)

    difference = None if birthday_star is None else birthday_star.difference_ly
    assert difference == expected_difference


def test_empty_catalogue_reaches_no_stars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stars, "NEARBY_STARS", [])

    result = _with_stars()

    assert (
        result.stars_reached,
        result.naked_eye_stars_reached,
        result.stars_reached_this_year,
        result.stars,
        result.stars_remaining,
        result.birthday_star,
        result.next_star,
    ) == (0, 0, 0, [], None, None, None)


def test_estimated_exoplanets_counts_only_the_stars_reached() -> None:
    result = FirstLightResponse(birthday="2000-01-01", as_of="2010-01-01")

    stars.add_exoplanets(result, stars.stars_reached(10.0))

    assert result.estimated_exoplanets == 17


@pytest.mark.parametrize(
    ("exoplanets", "habitable"),
    [
        pytest.param(0, 0, id="none"),
        pytest.param(7, 0, id="0.49-rounds-down"),
        pytest.param(8, 1, id="0.56-rounds-up"),
        pytest.param(122, 9, id="recorded-122-planets"),
    ],
)
def test_potentially_habitable_is_seven_percent_rounded(
    exoplanets: int, habitable: int
) -> None:
    result = FirstLightResponse(birthday="2000-01-01", as_of="2010-01-01")

    stars.add_exoplanets(result, [{"known_exoplanets": exoplanets}])

    assert result.potentially_habitable == habitable


def test_star_type_breakdown_counts_the_stars_reached_by_class() -> None:
    result = FirstLightResponse(birthday="2000-01-01", as_of="2010-01-01")

    stars.add_star_classification(result, stars.stars_reached(10.0))

    assert result.star_type_breakdown == {
        "Red dwarf (M)": 2,
        "Sun-like (G)": 1,
        "White (A)": 1,
        "Subdwarf (S)": 1,
        "Unknown": 1,
        "Other (X)": 1,
    }


@pytest.mark.parametrize(
    ("spectral_type", "expected"),
    [
        pytest.param("O9V", "Blue giant (O)", id="O"),
        pytest.param("B2IV", "Blue-white (B)", id="B"),
        pytest.param("A1V", "White (A)", id="A"),
        pytest.param("F5V", "Yellow-white (F)", id="F"),
        pytest.param("G2V", "Sun-like (G)", id="G"),
        pytest.param("K5V", "Orange dwarf (K)", id="K"),
        pytest.param("M5.5Ve", "Red dwarf (M)", id="M"),
        pytest.param("L2", "Brown dwarf (L)", id="L"),
        pytest.param("T6", "Brown dwarf (T)", id="T"),
        pytest.param("Y0", "Sub-brown dwarf (Y)", id="Y"),
        pytest.param("DA2", "White dwarf (D)", id="D"),
        pytest.param("g2v", "Sun-like (G)", id="lower-case"),
        pytest.param("sdM1", "Subdwarf (S)", id="sd"),
        pytest.param("esdK7", "Subdwarf (S)", id="esd"),
        pytest.param("usdM9", "Subdwarf (S)", id="usd"),
        pytest.param("X9", "Other (X)", id="unknown-letter"),
        pytest.param("x9", "Other (X)", id="unknown-lower-case"),
        pytest.param("", "Unknown", id="empty"),
    ],
)
def test_classify_spectral_names_the_class(
    spectral_type: str, expected: str
) -> None:
    assert stars.classify_spectral(spectral_type) == expected


@pytest.mark.parametrize(
    ("spectral_type", "expected"),
    [
        pytest.param("O9.5Iab", "Blue giant (O)", id="O-Iab"),
        pytest.param("B8Ia", "Blue giant (B)", id="B-Ia"),
        pytest.param("A2Ia", "White giant (A)", id="A-Ia"),
        pytest.param("F0Ia", "Yellow-white giant (F)", id="F-Ia"),
        pytest.param("F7Ib", "Yellow-white giant (F)", id="F-Ib"),
        pytest.param("G8III-IV", "Yellow giant (G)", id="G-III-to-IV"),
        pytest.param(
            "K1.5III", "Orange giant (K)", id="K-III-decimal-subclass"
        ),
        pytest.param("K0IIIb", "Orange giant (K)", id="K-IIIb"),
        pytest.param("K3II", "Orange giant (K)", id="K-II"),
        pytest.param("M0 IIIe", "Red giant (M)", id="M-III-after-a-space"),
        pytest.param("K0/K1III", "Orange giant (K)", id="K-range-III"),
        pytest.param("G8/K0III/IV", "Yellow giant (G)", id="G-to-K-range-III"),
        pytest.param("M1-2Ia-Iab", "Red giant (M)", id="M-subclass-range-Ia"),
        pytest.param(
            "F2mF5IIp", "Yellow-white giant (F)", id="F-metallic-line-II"
        ),
    ],
)
def test_luminosity_class_i_to_iii_gives_a_giant_label(
    spectral_type: str, expected: str
) -> None:
    assert stars.classify_spectral(spectral_type) == expected


@pytest.mark.parametrize(
    ("spectral_type", "expected"),
    [
        pytest.param("B9IV", "Blue-white (B)", id="B-IV"),
        pytest.param("G5IV-V", "Sun-like (G)", id="G-IV-to-V"),
        pytest.param("K0IV", "Orange dwarf (K)", id="K-IV"),
        pytest.param("M4.5V", "Red dwarf (M)", id="M-V"),
        pytest.param("F5-G0V", "Yellow-white (F)", id="F-to-G-range-V"),
        pytest.param("B9IV/V", "Blue-white (B)", id="B-IV-or-V"),
        pytest.param("K2:III:", "Orange dwarf (K)", id="K-uncertain"),
        pytest.param("A5mF2 (IV)", "White (A)", id="A-metallic-line-IV"),
    ],
)
def test_luminosity_class_iv_or_v_keeps_the_dwarf_label(
    spectral_type: str, expected: str
) -> None:
    assert stars.classify_spectral(spectral_type) == expected


@pytest.mark.parametrize(
    "name", ["Arcturus", "Pollux"], ids=["arcturus", "pollux"]
)
def test_shipped_k_giant_is_labelled_an_orange_giant(name: str) -> None:
    star = next(star for star in SHIPPED_STARS if star["name"] == name)

    assert stars.classify_spectral(star["spectral_type"]) == "Orange giant (K)"
