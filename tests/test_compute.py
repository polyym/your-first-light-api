"""Tests for the astronomy computation engine."""

import re
from datetime import date

import pytest

from src.compute import (
    _interpolate_distance,
    classify_spectral,
    compute_first_light,
    compute_moon_phase,
    compute_sun_constellation,
    count_eclipses,
    count_full_moons,
    count_leap_years,
    find_birthday_star,
    format_arrival_date,
    make_apod_url,
    next_full_moon,
    zodiac_sign_for,
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

    def test_full_moon_on_as_of_day_is_counted(self):
        """The end day is inclusive: a full moon later that day
        counts, consistent with compute_moon_phase labelling the
        same date "Full Moon"."""
        assert count_full_moons(
            date(2024, 1, 25), date(2024, 1, 26),
        ) == 1

    def test_hours_before_exact_full_is_full_moon(self):
        """Full moon 2024-06-22 01:08 UTC: at midnight the moon
        is ~99.99% lit and must not be labelled Waxing Gibbous."""
        phase = compute_moon_phase(date(2024, 6, 22))
        assert phase.phase_name == "Full Moon"
        assert phase.illumination_percent > 99

    def test_hours_before_new_moon_wraps_to_new(self):
        """New moon 2024-09-03 01:56 UTC: the tail of the cycle
        wraps back to New Moon rather than Waning Crescent."""
        phase = compute_moon_phase(date(2024, 9, 3))
        assert phase.phase_name == "New Moon"
        assert phase.illumination_percent < 1

    def test_next_full_moon_known_dates(self):
        # Real full moons: 2024-02-24 and 2025-07-10.
        assert next_full_moon(date(2024, 1, 27)) == "2024-02-24"
        assert next_full_moon(date(2025, 6, 15)) == "2025-07-10"

    def test_next_full_moon_later_same_day(self):
        """A full moon later on the reference day counts as the
        next one (the reference point is midnight UTC)."""
        assert next_full_moon(date(2024, 1, 26)) == "2024-01-26"


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


class TestArrivalDates:
    """Unit tests for calendar arrival-date formatting."""

    def test_matches_previous_astropy_output(self):
        # Same value the astropy Time path produced for Proxima
        # light arrival from a 2000-06-15 birth.
        assert format_arrival_date(
            date(2000, 6, 15), 4.2465 * 365.25,
        ) == "2004-09-13"

    def test_year_below_1000_is_zero_padded(self):
        s = format_arrival_date(
            date(900, 4, 1), 4.2465 * 365.25,
        )
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)
        assert s.startswith("0904-")

    def test_year_beyond_9999_is_well_formed(self):
        # 146,097 days is exactly 400 Gregorian years.
        s = format_arrival_date(date(9999, 1, 1), 146_100)
        assert s == "10399-01-04"

    def test_first_day_beyond_date_max(self):
        assert format_arrival_date(
            date(9999, 12, 31), 1,
        ) == "10000-01-01"

    def test_arrival_dates_via_compute(self):
        r = compute_first_light(
            date(900, 1, 1), date(910, 1, 1), {"stars"}, 5,
        )
        assert r.stars
        for s in r.stars:
            assert re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", s.light_arrival_date,
            ), s.light_arrival_date

    def test_next_star_arrival_beyond_9999(self):
        r = compute_first_light(
            date(9998, 1, 1), date(9999, 1, 1), {"stars"}, 5,
        )
        assert r.next_star is not None
        assert re.fullmatch(
            r"\d{5}-\d{2}-\d{2}", r.next_star.arrival_date,
        ), r.next_star.arrival_date


class TestEclipseCatalog:
    """Unit tests for eclipse catalogue lookups."""

    def test_known_eclipse_count(self):
        # Exact counts for a fixed range: the catalogue is
        # checked in, so these are stable and a regression in
        # either the data or the bisect logic fails loudly.
        ec = count_eclipses(date(2000, 1, 1), date(2025, 1, 1))
        assert ec.solar_eclipses == 56
        assert ec.lunar_eclipses == 57
        assert ec.total_eclipses == 113

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

    def test_next_eclipses_after_reference(self):
        # Real events: partial solar 2025-03-29, total lunar
        # 2025-03-14.
        ec = count_eclipses(date(2000, 1, 1), date(2025, 1, 1))
        assert ec.next_solar_eclipse == "2025-03-29"
        assert ec.next_lunar_eclipse == "2025-03-14"

    def test_next_eclipse_is_strictly_after_ref(self):
        """An eclipse ON the reference day is not 'next'."""
        ec = count_eclipses(date(2024, 4, 8), date(2024, 4, 8))
        assert ec.next_solar_eclipse is not None
        assert ec.next_solar_eclipse > "2024-04-08"

    def test_next_eclipses_absent_beyond_catalogue(self):
        ec = count_eclipses(date(2000, 1, 1), date(2101, 6, 1))
        assert ec.next_solar_eclipse is None
        assert ec.next_lunar_eclipse is None


class TestSunConstellation:
    """The Sun's actual constellation versus the zodiac sign."""

    def test_zodiac_sign_boundaries(self):
        assert zodiac_sign_for(date(2000, 1, 10)) == "Capricorn"
        assert zodiac_sign_for(date(2000, 1, 20)) == "Aquarius"
        assert zodiac_sign_for(date(2000, 12, 22)) == "Capricorn"
        assert zodiac_sign_for(date(2000, 12, 21)) == "Sagittarius"
        assert zodiac_sign_for(date(2000, 7, 23)) == "Leo"

    def test_ophiuchus_birthday(self):
        """Early December Sun sits in Ophiuchus, the thirteenth
        constellation no zodiac sign exists for."""
        sc = compute_sun_constellation(date(2000, 12, 5))
        assert sc.constellation == "Ophiuchus"
        assert sc.zodiac_sign == "Sagittarius"
        assert sc.matches_zodiac_sign is False

    def test_precession_shift_case(self):
        """Late March 'Aries' birthdays actually have the Sun
        in Pisces."""
        sc = compute_sun_constellation(date(1990, 3, 25))
        assert sc.constellation == "Pisces"
        assert sc.zodiac_sign == "Aries"
        assert sc.matches_zodiac_sign is False

    def test_matching_case(self):
        """Late August is one of the few stretches where sign
        and constellation still agree."""
        sc = compute_sun_constellation(date(2000, 8, 20))
        assert sc.constellation == "Leo"
        assert sc.zodiac_sign == "Leo"
        assert sc.matches_zodiac_sign is True

    def test_scorpius_name_mapping(self):
        """The brief Scorpius transit must compare via the IAU
        spelling, not the sign name Scorpio."""
        # Sun crosses Scorpius roughly 23-29 November.
        sc = compute_sun_constellation(date(2000, 11, 26))
        assert sc.constellation == "Scorpius"
        assert sc.zodiac_sign == "Sagittarius"
        assert sc.matches_zodiac_sign is False


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
