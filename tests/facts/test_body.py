"""Tests for the rough figures of what a body has done in a lifetime."""

from datetime import date

import pytest

from first_light.facts.age import Lifetime
from first_light.facts.body import add_body_stats
from first_light.models import BodyStats, FirstLightResponse

# 1988-03-21 to 2026-11-18: 14,121 days and 13 leap seconds, so
# 20,334,240 whole minutes. Expected values were worked by hand and
# match a recorded response.
LIFE = Lifetime(
    birth=date(1988, 3, 21),
    as_of=date(2026, 11, 18),
    years=1_220_054_413 / 31_557_600,
    days=14_121,
    seconds=1_220_054_413,
)


def _body_stats() -> BodyStats:
    result = FirstLightResponse(birthday="1988-03-21", as_of="2026-11-18")
    add_body_stats(result, LIFE)
    assert result.body_stats is not None
    return result.body_stats


def test_heartbeats_breaths_and_waking_blinks_count_whole_minutes() -> None:
    stats = _body_stats()

    assert (
        stats.estimated_heartbeats,
        stats.estimated_breaths,
        stats.estimated_blinks,
    ) == (1_464_065_280, 305_013_600, 230_454_720)


def test_photons_emitted_count_mean_infrared_photons() -> None:
    assert _body_stats().photons_emitted == pytest.approx(
        9.409084044506195e31, rel=1e-12
    )


def test_net_thermal_power_is_emission_less_absorption_near_180_w() -> None:
    assert _body_stats().thermal_power_watts == 180.06
