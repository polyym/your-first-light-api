"""Consistency of the hand-verified tables."""

import numpy as np
import pytest

from tools.updaters.stars.astrometry import (
    ARCSEC_PER_DEG,
    GAIA_DR3_EPOCH_JD,
    angular_sep_deg,
    parallax_to_ly,
    propagate_to_j2000,
)
from tools.updaters.stars.curated import (
    EXTRA_STARS,
    HIP_COMMON_NAMES,
    KNOWN_STAR_OVERRIDES,
    REFERENCE_POSITIONS,
    SPURIOUS_HIP_IDS,
)

# SIMBAD's parallax of each, in milliarcseconds. Early estimates put
# four of these objects 22 to 49 per cent too near.
_EXTRA_STAR_PARALLAXES_MAS = {
    "WISE 1506+7027": 193.9412,
    "WISE 0350-5658": 176.4,
    "LP 944-20": 155.5982,
    "WISE 1541-2250": 166.9,
    "SCR 1845-6357 A": 249.6651,
    "SCR J1546-5534": 119.0962,
}

# Luhman 16 A and B where SIMBAD puts them, at Gaia's epoch J2016.0,
# and the pair's proper motion in milliarcseconds a year. It carries
# them 44 arcseconds between J2000.0 and that epoch.
_LUHMAN_16_J2016_POSITIONS = {
    "Luhman 16A": (162.3084327, -53.3180570),
    "Luhman 16B": (162.3086437, -53.3182778),
}
_LUHMAN_16_PMRA_MAS_YR = -2767.502
_LUHMAN_16_PMDEC_MAS_YR = 356.856
_LUHMAN_16_PARALLAX_MAS = 500.0
# A curated position is rounded to four decimals of a degree.
_CURATED_POSITION_TOLERANCE_ARCSEC = 0.5

# The planets the NASA Exoplanet Archive listed for each overridden
# host in November 2026; it listed none for the other overridden stars.
_ARCHIVE_PLANETS_NOVEMBER_2026 = {
    "Proxima Centauri": 2,
    "Barnard's Star": 4,
    "Lalande 21185": 2,
    "Epsilon Eridani": 1,
    "Lacaille 9352": 4,
    "Ross 128": 1,
    "Groombridge 34 A": 2,
    "Tau Ceti": 3,
    "Epsilon Indi A": 1,
    "Luyten's Star": 2,
    "YZ Ceti": 3,
    "Kapteyn's Star": 1,
    "Pollux": 1,
}
# The same for the extra stars; it listed none for the other extras.
_ARCHIVE_PLANETS_OF_EXTRAS_NOVEMBER_2026 = {
    "Struve 2398 A": 1,
    "Struve 2398 B": 1,
    "GJ 1061": 3,
    "Teegarden's Star": 3,
    "GJ 876": 4,
    "GJ 832": 1,
    "TRAPPIST-1": 7,
    "LP 890-9": 2,
}


def test_hip_names_are_unique():
    names = list(HIP_COMMON_NAMES.values())
    assert len(names) == len(set(names))


def test_no_spurious_entry_has_a_name_or_is_a_reference():
    assert not SPURIOUS_HIP_IDS & set(HIP_COMMON_NAMES)
    assert not {str(n) for n in SPURIOUS_HIP_IDS} & set(
        REFERENCE_POSITIONS["hipparcos"]
    )


def test_no_name_is_both_extra_and_overridden():
    extras = {e["name"] for e in EXTRA_STARS}
    assert not extras & set(KNOWN_STAR_OVERRIDES)


def test_extra_star_distances_follow_their_parallaxes():
    extras = {e["name"]: e for e in EXTRA_STARS}
    for name, parallax_mas in _EXTRA_STAR_PARALLAXES_MAS.items():
        assert extras[name]["distance_ly"] == pytest.approx(
            parallax_to_ly(parallax_mas), abs=0.005
        )
    assert extras["SCR J1546-5534"]["spectral_type"] == "M7.5V"


def test_override_planet_counts_are_the_archives():
    """The fallback for a refresh whose archive answer lacks the star."""
    planets = {
        name: row["known_exoplanets"]
        for name, row in KNOWN_STAR_OVERRIDES.items()
        if row["known_exoplanets"]
    }
    assert planets == _ARCHIVE_PLANETS_NOVEMBER_2026


def test_extra_star_planet_counts_are_the_archives():
    """The fallback for a refresh whose archive answer lacks the star."""
    planets = {
        extra["name"]: extra["known_exoplanets"]
        for extra in EXTRA_STARS
        if extra["known_exoplanets"]
    }
    assert planets == _ARCHIVE_PLANETS_OF_EXTRAS_NOVEMBER_2026


def test_luhman_16_is_placed_at_epoch_j2000():
    extras = {e["name"]: e for e in EXTRA_STARS}
    for name, (ra_j2016, dec_j2016) in _LUHMAN_16_J2016_POSITIONS.items():
        ra, dec = propagate_to_j2000(
            np.array([ra_j2016]),
            np.array([dec_j2016]),
            np.array([_LUHMAN_16_PMRA_MAS_YR]),
            np.array([_LUHMAN_16_PMDEC_MAS_YR]),
            np.array([_LUHMAN_16_PARALLAX_MAS]),
            GAIA_DR3_EPOCH_JD,
        )
        sep_deg = angular_sep_deg(
            extras[name]["ra_deg"], extras[name]["dec_deg"], ra[0], dec[0]
        )
        assert sep_deg * ARCSEC_PER_DEG < _CURATED_POSITION_TOLERANCE_ARCSEC


def test_curated_coordinates_are_in_range():
    rows = [*KNOWN_STAR_OVERRIDES.values(), *EXTRA_STARS]
    for row in rows:
        assert 0 <= row["ra_deg"] < 360
        assert -90 <= row["dec_deg"] <= 90


def test_reference_stars_agree_across_sources():
    """The reference stars are the same objects in every catalogue."""
    assert (
        list(REFERENCE_POSITIONS["hipparcos"].values())
        == list(REFERENCE_POSITIONS["gliese"].values())
        == list(REFERENCE_POSITIONS["gaia"].values())
    )
