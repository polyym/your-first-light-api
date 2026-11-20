"""Rough figures for what a human body has done in a lifetime."""

from first_light.facts.age import Lifetime
from first_light.facts.physics import (
    BOLTZMANN_J_K,
    STEFAN_BOLTZMANN_W_M2_K4,
)
from first_light.models import BodyStats, FirstLightResponse

BODY_TEMP_K = 310.15  # 37 °C
AMBIENT_TEMP_K = 293.15  # A 20 °C room
BODY_SURFACE_AREA_M2 = 1.7  # An average adult
HEARTBEATS_PER_MIN = 72  # At rest
BREATHS_PER_MIN = 15
BLINKS_PER_WAKING_MIN = 17
WAKING_FRACTION = 2 / 3  # About 16 hours a day
# The mean photon energy of blackbody radiation at body temperature,
# 2.701 k T. Dividing by it counts the photons emitted; the energy at
# the Wien peak would undercount them by a factor of about 1.7.
MEAN_IR_PHOTON_ENERGY_J = 2.701 * BOLTZMANN_J_K * BODY_TEMP_K


def add_body_stats(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the body_stats category."""
    emitted_w = STEFAN_BOLTZMANN_W_M2_K4 * BODY_SURFACE_AREA_M2 * BODY_TEMP_K**4
    absorbed_w = (
        STEFAN_BOLTZMANN_W_M2_K4 * BODY_SURFACE_AREA_M2 * AMBIENT_TEMP_K**4
    )
    result.body_stats = BodyStats(
        estimated_heartbeats=int(HEARTBEATS_PER_MIN * life.minutes),
        estimated_breaths=int(BREATHS_PER_MIN * life.minutes),
        estimated_blinks=int(
            BLINKS_PER_WAKING_MIN * (life.minutes * WAKING_FRACTION)
        ),
        photons_emitted=(emitted_w / MEAN_IR_PHOTON_ENERGY_J) * life.seconds,
        thermal_power_watts=round(emitted_w - absorbed_w, 2),
    )
