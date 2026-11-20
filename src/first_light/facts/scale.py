"""The size of the light sphere, and journeys to put it in scale."""

import math

from astropy import units as u

from first_light.facts.age import Lifetime
from first_light.facts.physics import (
    EARTH_ORBITAL_SPEED_KM_S,
    EARTH_VOLUME_KM3,
    GALACTIC_ORBITAL_PERIOD_MYR,
    GREAT_ATTRACTOR_SPEED_KM_S,
    HOURS_PER_YEAR,
    HUBBLE_CONSTANT_KM_S_MPC,
    LIGHT_SPEED_KM_S,
    LY_KM,
    MILKY_WAY_DIAMETER_LY,
    MOON_DISTANCE_KM,
    MPC_KM,
    OBSERVABLE_UNIVERSE_DIAMETER_LY,
    PLUTO_DISTANCE_KM,
    SECONDS_PER_YEAR,
    SUN_DISTANCE_KM,
    SUN_GALACTIC_ORBITAL_SPEED_KM_S,
    UNIVERSE_AGE_YEARS,
)
from first_light.facts.voyagers import VOYAGER_1_SPEED_KM_S
from first_light.models import (
    CosmicJourney,
    FirstLightResponse,
    LightSphere,
    ScaleComparison,
)

CAR_SPEED_KM_H = 100
JET_SPEED_KM_H = 900


def add_light_sphere(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the light_sphere category."""
    radius_ly = life.years
    diameter_ly = radius_ly * 2
    result.light_sphere = LightSphere(
        radius_ly=round(radius_ly, 2),
        diameter_ly=round(diameter_ly, 2),
        radius_km=round(_radius_km(life), 2),
        radius_au=round((radius_ly * u.lyr).to(u.AU).value, 2),
        volume_cubic_ly=round(_volume_ly3(life), 2),
        surface_area_sq_ly=round(4 * math.pi * radius_ly**2, 2),
        milky_way_diameter_percent=round(
            (diameter_ly / MILKY_WAY_DIAMETER_LY) * 100, 6
        ),
        observable_universe_diameter_percent=round(
            (diameter_ly / OBSERVABLE_UNIVERSE_DIAMETER_LY) * 100, 12
        ),
    )
    result.speed_of_light_km_s = LIGHT_SPEED_KM_S


def add_cosmic_journey(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the cosmic_journey category."""
    result.cosmic_journey = CosmicJourney(
        earth_distance_around_sun_km=round(
            EARTH_ORBITAL_SPEED_KM_S * life.seconds, 2
        ),
        earth_orbits_completed=round(life.years, 2),
        galactic_distance_km=round(_galactic_km(life), 2),
        galactic_orbit_degrees=round(
            (life.years / (GALACTIC_ORBITAL_PERIOD_MYR * 1e6)) * 360, 6
        ),
        great_attractor_distance_km=round(
            GREAT_ATTRACTOR_SPEED_KM_S * life.seconds, 2
        ),
        # First-order Hubble expansion: H0 times the time elapsed.
        universe_expansion_percent=round(
            ((HUBBLE_CONSTANT_KM_S_MPC * life.seconds) / MPC_KM) * 100, 10
        ),
    )


def add_scale_comparisons(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the scale_comparisons category."""
    radius_km = _radius_km(life)
    diameter_km = radius_km * 2
    comparisons = [
        ("Trips to the Moon", radius_km / MOON_DISTANCE_KM, "trips"),
        ("Trips to the Sun", radius_km / SUN_DISTANCE_KM, "trips"),
        ("Trips to Pluto", radius_km / PLUTO_DISTANCE_KM, "trips"),
        (
            f"Time to cross your light sphere by car at {CAR_SPEED_KM_H} km/h",
            diameter_km / CAR_SPEED_KM_H / HOURS_PER_YEAR,
            "years",
        ),
        (
            f"Time to cross by commercial jet at {JET_SPEED_KM_H} km/h",
            diameter_km / JET_SPEED_KM_H / HOURS_PER_YEAR,
            "years",
        ),
        (
            f"Time to cross at Voyager 1 speed ({VOYAGER_1_SPEED_KM_S:g} km/s)",
            diameter_km / VOYAGER_1_SPEED_KM_S / SECONDS_PER_YEAR,
            "years",
        ),
        (
            "Earths that could fit inside your light sphere by volume",
            _volume_ly3(life) * LY_KM**3 / EARTH_VOLUME_KM3,
            "earths",
        ),
        (
            "Distance travelled through space via galactic orbit",
            _galactic_km(life),
            "km",
        ),
    ]
    result.scale_comparisons = [
        ScaleComparison(label=label, value=round(value, 2), unit=unit)
        for label, value, unit in comparisons
    ]


def add_universe_perspective(
    result: FirstLightResponse, life: Lifetime
) -> None:
    """Fills the universe_perspective category."""
    result.universe_age_percent = round(
        (life.years / UNIVERSE_AGE_YEARS) * 100, 15
    )


def _radius_km(life: Lifetime) -> float:
    # A numpy float, a subclass of float. Converting it would change how
    # round() treats the last digit of a 15-digit number.
    radius_km: float = (life.years * u.lyr).to(u.km).value
    return radius_km


def _volume_ly3(life: Lifetime) -> float:
    return (4 / 3) * math.pi * life.years**3


def _galactic_km(life: Lifetime) -> float:
    return SUN_GALACTIC_ORBITAL_SPEED_KM_S * life.seconds
