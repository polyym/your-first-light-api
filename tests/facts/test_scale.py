"""Tests for the light sphere and the journeys that put it in scale."""

from datetime import date

import pytest

from first_light.facts import scale
from first_light.facts.age import Lifetime, measure_lifetime
from first_light.models import FirstLightResponse

# 1988-03-21 to 2026-11-18: 14,121 days and 13 leap seconds. Expected
# values were worked by hand and match a recorded response.
LIFE = Lifetime(
    birth=date(1988, 3, 21),
    as_of=date(2026, 11, 18),
    years=1_220_054_413 / 31_557_600,
    days=14_121,
    seconds=1_220_054_413,
)


def _empty() -> FirstLightResponse:
    return FirstLightResponse(birthday="1988-03-21", as_of="2026-11-18")


def test_light_sphere_for_a_fixed_lifetime() -> None:
    result = _empty()

    scale.add_light_sphere(result, LIFE)

    assert result.light_sphere is not None
    assert result.light_sphere.model_dump() == {
        "radius_ly": 38.66,
        "diameter_ly": 77.32,
        "radius_km": 365_763_111_367_017.2,
        "radius_au": 2_444_975.38,
        "volume_cubic_ly": 242_055.14,
        "surface_area_sq_ly": 18_782.8,
        "milky_way_diameter_percent": 0.08847,
        "observable_universe_diameter_percent": 8.3128e-8,
    }


@pytest.mark.parametrize(
    ("birth", "expected"),
    [
        # radius_km ends in a digit that plain-float rounding gets wrong.
        pytest.param(
            date(2007, 8, 4),
            {
                "radius_ly": 19.29,
                "diameter_ly": 38.58,
                "radius_km": 182_505_974_942_645.1,
                "radius_au": 1_219_977.09,
                "volume_cubic_ly": 30_070.86,
                "surface_area_sq_ly": 4_676.43,
                "milky_way_diameter_percent": 0.044144,
                "observable_universe_diameter_percent": 4.1479e-8,
            },
            id="born-2007",
        ),
        # Two millennia make a small error in a unit conversion show.
        pytest.param(
            date(1, 1, 1),
            {
                "radius_ly": 2025.84,
                "diameter_ly": 4051.67,
                "radius_km": 1.9165898775472936e16,
                "radius_au": 128_116_120.14,
                "volume_cubic_ly": 34_825_885_638.72,
                "surface_area_sq_ly": 51_572_585.46,
                "milky_way_diameter_percent": 4.635783,
                "observable_universe_diameter_percent": 4.35589e-6,
            },
            id="born-year-1",
        ),
    ],
)
def test_light_sphere_to_2026_11_18_matches_recorded_responses(
    birth: date, expected: dict[str, float]
) -> None:
    as_of = date(2026, 11, 18)
    result = FirstLightResponse(
        birthday=birth.isoformat(), as_of=as_of.isoformat()
    )

    scale.add_light_sphere(result, measure_lifetime(birth, as_of))

    assert result.light_sphere is not None
    assert result.light_sphere.model_dump() == expected


def test_light_sphere_gives_the_speed_of_light() -> None:
    result = _empty()

    scale.add_light_sphere(result, LIFE)

    assert result.speed_of_light_km_s == 299_792.458


def test_scale_comparison_labels_and_units_in_order() -> None:
    result = _empty()

    scale.add_scale_comparisons(result, LIFE)

    assert result.scale_comparisons is not None
    assert [(row.label, row.unit) for row in result.scale_comparisons] == [
        ("Trips to the Moon", "trips"),
        ("Trips to the Sun", "trips"),
        ("Trips to Pluto", "trips"),
        ("Time to cross your light sphere by car at 100 km/h", "years"),
        ("Time to cross by commercial jet at 900 km/h", "years"),
        ("Time to cross at Voyager 1 speed (17 km/s)", "years"),
        ("Earths that could fit inside your light sphere by volume", "earths"),
        ("Distance travelled through space via galactic orbit", "km"),
    ]


def test_scale_comparison_values_for_a_fixed_lifetime() -> None:
    result = _empty()

    scale.add_scale_comparisons(result, LIFE)

    assert result.scale_comparisons is not None
    assert [row.value for row in result.scale_comparisons] == pytest.approx(
        [
            951_516_939.04,
            2_444_975.38,
            61_926.82,
            834_504_018.63,
            92_722_668.74,
            1_363_568.66,
            1.892237555765406e32,
            280_612_514_990.0,
        ],
        rel=1e-12,
    )


def test_cosmic_journey_for_a_fixed_lifetime() -> None:
    result = _empty()

    scale.add_cosmic_journey(result, LIFE)

    assert result.cosmic_journey is not None
    assert result.cosmic_journey.model_dump() == {
        "earth_distance_around_sun_km": 36_333_220_419.14,
        "earth_orbits_completed": 38.66,
        "galactic_distance_km": 280_612_514_990.0,
        "galactic_orbit_degrees": 0.000062,
        "great_attractor_distance_km": 732_032_647_800.0,
        "universe_expansion_percent": 2.768e-7,
    }


def test_universe_age_percent_for_a_fixed_lifetime() -> None:
    result = _empty()

    scale.add_universe_perspective(result, LIFE)

    assert result.universe_age_percent == 2.80417722e-7
