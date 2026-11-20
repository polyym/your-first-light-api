"""Every source catalogue is moved to epoch J2000.0 from its own epoch."""

import math

import numpy as np
import pytest

from tools.updaters.stars.astrometry import (
    ARCSEC_PER_DEG,
    B1950_JD,
    GAIA_DR3_EPOCH_JD,
    HIPPARCOS_EPOCH_JD,
    UNKNOWN_SEP_DEG,
    angular_sep_deg,
    gliese_b1950_to_icrs,
    propagate_to_j2000,
)

# SIMBAD ICRS J2000.0 positions.
BARNARDS_STAR = (269.45208, 4.69336)
GROOMBRIDGE_1830 = (178.24487, 37.71868)


def _sep_arcsec(ra: float, dec: float, target: tuple[float, float]) -> float:
    return angular_sep_deg(ra, dec, *target) * ARCSEC_PER_DEG


@pytest.mark.parametrize(
    ("first", "second", "separation"),
    [
        ((0.0, 0.0), (90.0, 0.0), 90.0),
        ((0.0, 45.0), (90.0, 45.0), 60.0),
        ((0.0, 0.0), (180.0, 0.0), 180.0),
        ((40.0, -90.0), (220.0, 90.0), 180.0),
        ((10.0, 60.0), (190.0, 60.0), 60.0),
        ((10.0, 60.0), (10.0, 60.0), 0.0),
    ],
    ids=[
        "a-quarter-turn-of-ra",
        "a-quarter-turn-at-45-degrees",
        "opposite-on-the-equator",
        "pole-to-pole",
        "across-the-pole",
        "the-same-place",
    ],
)
def test_separation_is_the_angle_between_two_positions_on_the_sky(
    first, second, separation
):
    assert angular_sep_deg(*first, *second) == pytest.approx(separation)


@pytest.mark.parametrize(
    "missing", range(4), ids=["no-ra1", "no-dec1", "no-ra2", "no-dec2"]
)
def test_separation_with_a_coordinate_missing_is_unknown(missing):
    coordinates: list[float | None] = [10.0, 20.0, 10.0, 20.0]
    coordinates[missing] = None

    assert angular_sep_deg(*coordinates) == UNKNOWN_SEP_DEG


def test_gaia_epoch_2016_reaches_simbad_j2000():
    """Barnard's Star as Gaia DR3 4472832130942575872 lists it."""
    ra, dec = propagate_to_j2000(
        np.array([269.44850253]),
        np.array([4.73942005]),
        np.array([-801.551]),
        np.array([10362.394]),
        np.array([546.9759]),
        GAIA_DR3_EPOCH_JD,
    )
    assert _sep_arcsec(ra[0], dec[0], BARNARDS_STAR) < 0.5


def test_hipparcos_epoch_reaches_simbad_j2000():
    """Groombridge 1830 as HIP 57939 lists it."""
    ra, dec = propagate_to_j2000(
        np.array([178.23256802]),
        np.array([37.73280827]),
        np.array([4003.69]),
        np.array([-5813.00]),
        np.array([109.21]),
        HIPPARCOS_EPOCH_JD,
    )
    assert _sep_arcsec(ra[0], dec[0], GROOMBRIDGE_1830) < 0.5


def test_gliese_b1950_row_reaches_j2000():
    """Groombridge 1830 as the Gliese catalogue lists it.

    That is a B1950 position, a total proper motion and a position
    angle. Without the fifty years of motion the star sits some 350
    arcsec away, far enough to break the cross-catalogue match.
    """
    ra0, dec0 = gliese_b1950_to_icrs(["11 50 06"], ["+38 04.7"])
    assert _sep_arcsec(ra0[0], dec0[0], GROOMBRIDGE_1830) > 300
    pm, pa = 7.053, math.radians(145.4)
    ra, dec = propagate_to_j2000(
        ra0,
        dec0,
        np.array([pm * 1000 * math.sin(pa)]),
        np.array([pm * 1000 * math.cos(pa)]),
        np.array([116.0]),
        B1950_JD,
    )
    assert _sep_arcsec(ra[0], dec[0], GROOMBRIDGE_1830) < 10


def test_zero_proper_motion_is_identity():
    ra, dec = propagate_to_j2000(
        np.array([10.0]),
        np.array([-20.0]),
        np.array([0.0]),
        np.array([0.0]),
        np.array([50.0]),
        HIPPARCOS_EPOCH_JD,
    )
    assert abs(ra[0] - 10.0) < 1e-6
    assert abs(dec[0] + 20.0) < 1e-6


def test_missing_proper_motion_counts_as_zero():
    ra, dec = propagate_to_j2000(
        np.array([10.0]),
        np.array([-20.0]),
        np.array([np.nan]),
        np.array([np.nan]),
        np.array([np.nan]),
        GAIA_DR3_EPOCH_JD,
    )
    assert abs(ra[0] - 10.0) < 1e-6
    assert abs(dec[0] + 20.0) < 1e-6


def test_missing_position_stays_missing():
    ra, dec = propagate_to_j2000(
        np.array([np.nan, 1.0]),
        np.array([np.nan, 2.0]),
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        np.array([50.0, 50.0]),
        HIPPARCOS_EPOCH_JD,
    )
    assert np.isnan(ra[0]) and np.isnan(dec[0])
    assert abs(ra[1] - 1.0) < 1e-6
    ra0, dec0 = gliese_b1950_to_icrs([""], [""])
    assert np.isnan(ra0[0]) and np.isnan(dec0[0])
