"""Tests for the astronomy computation engine."""

from datetime import date

import pytest

from src.compute import (
    _interpolate_distance,
    classify_spectral,
    compute_moon_phase,
    count_eclipses,
    count_full_moons,
    count_leap_years,
    find_birthday_star,
    make_apod_url,
)
from src.constants import VOYAGER_1_MILESTONES


class TestMoonPhase:
    """Unit tests for moon phase computation and full-moon counting."""

    def test_known_full_moon(self):
        phase = compute_moon_phase(date(2024, 4, 24))
        assert phase.phase_name == "Full Moon"
        assert phase.illumination_percent > 98

    def test_known_new_moon(self):
        phase = compute_moon_phase(date(2000, 1, 7))
        assert phase.phase_name in ("New Moon", "Waxing Crescent")
        assert phase.illumination_percent < 2

    def test_first_quarter(self):
        # 2024-01-18 03:52 UTC is the exact first quarter;
        # at midnight the moon age is just under the threshold
        phase = compute_moon_phase(date(2024, 1, 18))
        assert phase.phase_name in (
            "Waxing Crescent", "First Quarter",
        )
        assert 40 < phase.illumination_percent < 60

    def test_full_moon_count(self):
        count = count_full_moons(
            date(2000, 1, 1), date(2001, 1, 1),
        )
        assert 12 <= count <= 13


class TestHelpers:
    """Unit tests for standalone compute helpers."""

    def test_classify_spectral(self):
        assert classify_spectral("G2V") == "Sun-like (G)"
        assert classify_spectral("M5.5V") == "Red dwarf (M)"
        assert classify_spectral("DA2") == "White dwarf (D)"
        assert classify_spectral("") == "Unknown"

    def test_count_leap_years(self):
        count = count_leap_years(
            date(2000, 1, 1), date(2004, 12, 31),
        )
        assert count == 2

    def test_count_leap_years_excludes_before_birth(self):
        count = count_leap_years(
            date(2000, 3, 1), date(2004, 12, 31),
        )
        assert count == 1

    def test_find_birthday_star_match(self):
        stars = [
            {"name": "Test", "distance_ly": 10.0,
             "spectral_type": "G2V"},
        ]
        result = find_birthday_star(10.5, stars)
        assert result is not None
        assert result.name == "Test"

    def test_find_birthday_star_too_far(self):
        stars = [
            {"name": "Test", "distance_ly": 10.0,
             "spectral_type": "G2V"},
        ]
        result = find_birthday_star(15.0, stars)
        assert result is None

    def test_make_apod_url_modern(self):
        url = make_apod_url(date(2002, 10, 14))
        assert url == "https://apod.nasa.gov/apod/ap021014.html"

    def test_make_apod_url_pre_apod(self):
        url = make_apod_url(date(1980, 1, 1))
        assert "astropix.html" in url


class TestEclipseCatalog:
    """Unit tests for eclipse catalogue lookups."""

    def test_known_eclipse_count(self):
        ec = count_eclipses(date(2000, 1, 1), date(2025, 1, 1))
        assert ec.solar_eclipses > 0
        assert ec.lunar_eclipses > 0
        assert ec.total_eclipses == (
            ec.solar_eclipses + ec.lunar_eclipses
        )

    def test_single_day_range(self):
        ec = count_eclipses(
            date(2020, 3, 15), date(2020, 3, 16),
        )
        assert ec.total_eclipses <= 1

    def test_known_solar_eclipse(self):
        ec = count_eclipses(
            date(2024, 4, 8), date(2024, 4, 8),
        )
        assert ec.solar_eclipses == 1

    def test_coverage_note_absent_for_normal_range(self):
        """No coverage note when both dates are within 1900-2100."""
        ec = count_eclipses(date(2000, 1, 1), date(2025, 1, 1))
        assert ec.coverage_note is None

    def test_coverage_note_for_pre_1900_birthday(self):
        """Coverage note when the birthday predates the catalogue."""
        ec = count_eclipses(date(1850, 1, 1), date(2025, 1, 1))
        assert ec.coverage_note is not None
        assert "1900-2100" in ec.coverage_note
        assert "1900-01-01" in ec.coverage_note
        assert "2025-01-01" in ec.coverage_note

    def test_coverage_note_for_post_2100_ref(self):
        """Coverage note when the reference date exceeds the catalogue."""
        ec = count_eclipses(date(2000, 1, 1), date(2110, 1, 1))
        assert ec.coverage_note is not None
        assert "2100-12-31" in ec.coverage_note

    def test_pre_1900_counts_are_zero(self):
        """Entirely pre-1900 range returns zero eclipses."""
        ec = count_eclipses(date(1850, 1, 1), date(1899, 12, 31))
        assert ec.total_eclipses == 0
        assert ec.coverage_note is not None


class TestVoyagerInterpolation:
    """Unit tests for Voyager distance interpolation."""

    def test_at_launch(self):
        d = _interpolate_distance(
            date(1977, 9, 5), VOYAGER_1_MILESTONES,
        )
        assert d == pytest.approx(1.01, abs=0.01)

    def test_mid_cruise(self):
        d = _interpolate_distance(
            date(2002, 7, 1), VOYAGER_1_MILESTONES,
        )
        assert 76 < d < 95

    def test_extrapolation_beyond_last(self):
        d = _interpolate_distance(
            date(2026, 1, 1), VOYAGER_1_MILESTONES,
        )
        assert 168 < d < 172

    def test_before_launch(self):
        d = _interpolate_distance(
            date(1970, 1, 1), VOYAGER_1_MILESTONES,
        )
        assert d == pytest.approx(1.01, abs=0.01)
