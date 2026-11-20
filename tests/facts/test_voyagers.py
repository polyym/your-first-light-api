"""Tests for how far the Voyager probes have flown in a lifetime."""

from datetime import date

import pytest

from first_light.facts.age import measure_lifetime
from first_light.facts.voyagers import (
    VOYAGER_1_MILESTONES,
    VOYAGER_2_MILESTONES,
    add_voyagers,
    distance_au,
)
from first_light.models import FirstLightResponse, VoyagerStatus

MILESTONES = {
    "Voyager 1": VOYAGER_1_MILESTONES,
    "Voyager 2": VOYAGER_2_MILESTONES,
}


def _voyagers(birth: date, as_of: date) -> list[VoyagerStatus]:
    result = FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )
    add_voyagers(result, measure_lifetime(birth, as_of))
    assert result.voyagers is not None
    return result.voyagers


@pytest.mark.parametrize(
    ("probe", "day", "expected_au"),
    [
        pytest.param("Voyager 1", date(1979, 3, 5), 5.28, id="v1-jupiter"),
        pytest.param("Voyager 1", date(1980, 11, 12), 9.51, id="v1-saturn"),
        pytest.param(
            "Voyager 1", date(2012, 8, 25), 121.60, id="v1-interstellar"
        ),
        pytest.param("Voyager 2", date(1979, 7, 9), 5.32, id="v2-jupiter"),
        pytest.param("Voyager 2", date(1981, 8, 26), 9.60, id="v2-saturn"),
        pytest.param("Voyager 2", date(1986, 1, 24), 19.12, id="v2-uranus"),
        pytest.param("Voyager 2", date(1989, 8, 25), 30.21, id="v2-neptune"),
        pytest.param(
            "Voyager 2", date(2018, 11, 5), 119.02, id="v2-interstellar"
        ),
    ],
)
def test_distance_on_a_milestone_is_its_distance(
    probe: str, day: date, expected_au: float
) -> None:
    assert distance_au(day, MILESTONES[probe]) == expected_au


# The distance from the Sun's centre on 1 January of each year, as
# (Voyager 1, Voyager 2) in AU, from JPL Horizons. Typed apart from the
# tables, so that a mistyped or missing milestone shows.
HORIZONS_1_JANUARY_AU = {
    1978: (1.92, 1.91),
    1979: (4.88, 4.49),
    1980: (6.90, 6.05),
    1981: (9.74, 8.09),
    1982: (12.06, 9.73),
    1983: (15.07, 10.99),
    1984: (18.39, 13.19),
    1985: (21.88, 15.93),
    1986: (25.44, 18.92),
    1987: (29.03, 21.72),
    1988: (32.65, 24.77),
    1989: (36.29, 28.04),
    1990: (39.92, 31.07),
    1991: (43.56, 33.60),
    1992: (47.19, 36.26),
    1993: (50.83, 39.02),
    1994: (54.46, 41.86),
    1995: (58.09, 44.75),
    1996: (61.71, 47.69),
    1997: (65.33, 50.68),
    1998: (68.94, 53.69),
    1999: (72.55, 56.73),
    2000: (76.16, 59.79),
    2001: (79.77, 62.87),
    2002: (83.38, 65.96),
    2003: (86.98, 69.06),
    2004: (90.57, 72.18),
    2005: (94.18, 75.31),
    2006: (97.77, 78.45),
    2007: (101.36, 81.58),
    2008: (104.95, 84.73),
    2009: (108.54, 87.88),
    2010: (112.12, 91.03),
    2011: (115.70, 94.19),
    2012: (119.28, 97.34),
    2013: (122.87, 100.51),
    2014: (126.44, 103.67),
    2015: (130.02, 106.83),
    2016: (133.59, 110.00),
    2017: (137.17, 113.17),
    2018: (140.74, 116.34),
    2019: (144.31, 119.51),
    2020: (147.88, 122.68),
    2021: (151.45, 125.86),
    2022: (155.01, 129.03),
    2023: (158.57, 132.20),
    2024: (162.13, 135.37),
    2025: (165.70, 138.54),
    2026: (169.26, 141.71),
}


@pytest.mark.parametrize("year", HORIZONS_1_JANUARY_AU)
def test_distance_on_1_january_is_the_one_jpl_horizons_gives(year: int) -> None:
    new_year = date(year, 1, 1)

    assert (
        distance_au(new_year, VOYAGER_1_MILESTONES),
        distance_au(new_year, VOYAGER_2_MILESTONES),
    ) == HORIZONS_1_JANUARY_AU[year]


# The most a distance between two milestones strays from JPL Horizons.
INTERPOLATION_SLACK_AU = 0.21


@pytest.mark.parametrize(
    ("probe", "day", "horizons_au"),
    [
        pytest.param(
            "Voyager 1", date(1978, 6, 23), 3.5092, id="v1-furthest-out"
        ),
        pytest.param(
            "Voyager 2", date(1978, 6, 23), 3.3364, id="v2-furthest-out"
        ),
        pytest.param("Voyager 1", date(1982, 6, 8), 13.3057, id="v1-1982"),
        pytest.param("Voyager 2", date(1983, 5, 31), 11.8092, id="v2-1983"),
        pytest.param("Voyager 2", date(1997, 5, 27), 51.8840, id="v2-1997"),
    ],
)
def test_distance_between_milestones_is_close_to_jpl_horizons(
    probe: str, day: date, horizons_au: float
) -> None:
    assert distance_au(day, MILESTONES[probe]) == pytest.approx(
        horizons_au, abs=INTERPOLATION_SLACK_AU
    )


@pytest.mark.parametrize(
    ("probe", "day", "expected_au"),
    [
        pytest.param(
            "Voyager 1", date(2016, 7, 2), (133.59 + 137.17) / 2, id="voyager-1"
        ),
        pytest.param(
            "Voyager 2", date(2008, 7, 2), (84.73 + 87.88) / 2, id="voyager-2"
        ),
    ],
)
def test_distance_halfway_between_milestones_is_their_mean(
    probe: str, day: date, expected_au: float
) -> None:
    assert distance_au(day, MILESTONES[probe]) == pytest.approx(
        expected_au, abs=1e-9
    )


@pytest.mark.parametrize(
    ("probe", "day", "expected_au"),
    [
        pytest.param("Voyager 1", date(1977, 9, 4), 1.01, id="voyager-1"),
        pytest.param("Voyager 2", date(1977, 8, 19), 1.01, id="voyager-2"),
    ],
)
def test_distance_before_launch_is_the_launch_distance(
    probe: str, day: date, expected_au: float
) -> None:
    assert distance_au(day, MILESTONES[probe]) == expected_au


@pytest.mark.parametrize(
    ("probe", "expected_au"),
    [
        pytest.param("Voyager 1", 169.26 + 3.56, id="voyager-1"),
        pytest.param("Voyager 2", 141.71 + 3.17, id="voyager-2"),
    ],
)
def test_distance_after_the_last_milestone_keeps_its_last_rate(
    probe: str, expected_au: float
) -> None:
    a_year_on = date(2027, 1, 1)

    assert distance_au(a_year_on, MILESTONES[probe]) == pytest.approx(
        expected_au, abs=1e-9
    )


def test_km_is_the_au_figure_times_149_597_870_7_km() -> None:
    probes = _voyagers(date(2000, 1, 1), date(2010, 1, 1))

    assert [
        (
            probe.distance_travelled_since_birth_au,
            probe.distance_travelled_since_birth_km,
        )
        for probe in probes
    ] == [(35.96, 5_379_539_430.37), (31.24, 4_673_437_480.67)]


# The flown distance is to 2026-01-01, a milestone for both probes.
LAUNCH_EDGES = [
    pytest.param(0, date(1977, 9, 4), False, 168.25, id="v1-day-before"),
    pytest.param(0, date(1977, 9, 5), False, 168.25, id="v1-launch-day"),
    pytest.param(0, date(1977, 9, 6), True, 168.24, id="v1-day-after"),
    pytest.param(1, date(1977, 8, 19), False, 140.70, id="v2-day-before"),
    pytest.param(1, date(1977, 8, 20), False, 140.70, id="v2-launch-day"),
    pytest.param(1, date(1977, 8, 21), True, 140.69, id="v2-day-after"),
]


@pytest.mark.parametrize(("index", "birth", "launched", "au"), LAUNCH_EDGES)
def test_launched_before_birth_only_for_a_launch_strictly_before(
    index: int, birth: date, launched: bool, au: float
) -> None:
    probe = _voyagers(birth, date(2026, 1, 1))[index]

    assert probe.was_launched_before_birth is launched


@pytest.mark.parametrize(("index", "birth", "launched", "au"), LAUNCH_EDGES)
def test_distance_flown_counts_from_launch_for_an_earlier_birthday(
    index: int, birth: date, launched: bool, au: float
) -> None:
    probe = _voyagers(birth, date(2026, 1, 1))[index]

    assert probe.distance_travelled_since_birth_au == au


def test_voyagers_match_a_recorded_lifetime() -> None:
    probes = _voyagers(date(1988, 3, 21), date(2026, 11, 18))

    assert [probe.model_dump() for probe in probes] == [
        {
            "name": "Voyager 1",
            "launch_date": "1977-09-05",
            "distance_travelled_since_birth_km": 20_785_909_190.55,
            "distance_travelled_since_birth_au": 138.95,
            "speed_km_s": 17.0,
            "was_launched_before_birth": True,
        },
        {
            "name": "Voyager 2",
            "launch_date": "1977-08-20",
            "distance_travelled_since_birth_km": 17_804_107_679.12,
            "distance_travelled_since_birth_au": 119.01,
            "speed_km_s": 15.4,
            "was_launched_before_birth": True,
        },
    ]
