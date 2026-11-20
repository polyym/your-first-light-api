"""Sky positions: units, catalogue epochs, propagation and separations.

The API publishes ICRS positions at epoch J2000.0. Each source
catalogue records positions at its own epoch (HIPPARCOS J1991.25, Gaia
DR3 J2016.0, Gliese B1950.0), and nearby stars move fast enough
(Barnard's Star about 10 arcsec a year) for the difference to reach
tens to hundreds of arcseconds. The fetchers therefore read each
catalogue's native position and proper motion and propagate them here,
rather than use VizieR's computed _RAJ2000/_DEJ2000 columns: VizieR
does not apply proper motion to those for every catalogue, and an
unpropagated Gliese position puts a fast mover far enough from its
HIPPARCOS and Gaia entries that the merge lists it twice.
"""

import math

import astropy.units as u
import erfa
import numpy as np
from astropy.coordinates import SkyCoord

LY_PER_PARSEC = 3.26156
MAS_PER_ARCSEC = 1000.0
ARCSEC_PER_DEG = 3600.0
MAS_PER_DEG = 3.6e6
DAYS_PER_JULIAN_YEAR = 365.25

J2000_JD = 2451545.0
B1950_JD = 2433282.4235  # Besselian epoch B1950.0
HIPPARCOS_EPOCH_JD = J2000_JD + (1991.25 - 2000.0) * DAYS_PER_JULIAN_YEAR
GAIA_DR3_EPOCH_JD = J2000_JD + (2016.0 - 2000.0) * DAYS_PER_JULIAN_YEAR

# Returned for a pair with a missing position: larger than any real
# separation and any matching radius, so such a pair never matches.
UNKNOWN_SEP_DEG = 999.0


def min_parallax_mas(max_dist_ly: float) -> float:
    """The parallax of a star at ``max_dist_ly``, in milliarcseconds."""
    return MAS_PER_ARCSEC / (max_dist_ly / LY_PER_PARSEC)


def parallax_to_ly(parallax_mas: float) -> float:
    """The distance in light-years of a star with this parallax."""
    return (MAS_PER_ARCSEC / parallax_mas) * LY_PER_PARSEC


def propagate_to_j2000(
    ra_deg: np.ndarray,
    dec_deg: np.ndarray,
    pmra_masyr: np.ndarray,
    pmde_masyr: np.ndarray,
    plx_mas: np.ndarray,
    epoch_jd: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Moves ICRS positions from a catalogue epoch to J2000.0.

    Uses ERFA's rigorous space-motion propagation (``pmsafe``),
    vectorised over the whole catalogue. The positions are at
    ``epoch_jd``, and the RA proper motion includes the cos(Dec)
    factor, as catalogues publish it. A missing proper motion counts as
    zero, and so does a missing parallax, which only affects the tiny
    perspective term.

    Returns:
        ``(ra, dec)`` arrays in degrees at epoch J2000.0, with RA in
        ``[0, 360)`` and NaN for rows with no usable position.
    """
    ra = np.asarray(ra_deg, dtype=float)
    dec = np.asarray(dec_deg, dtype=float)
    ok = np.isfinite(ra) & np.isfinite(dec)
    out_ra = np.full(ra.shape, np.nan)
    out_dec = np.full(dec.shape, np.nan)
    if not ok.any():
        return out_ra, out_dec

    ra_rad = np.radians(ra[ok])
    dec_rad = np.radians(dec[ok])
    pmra = np.nan_to_num(np.asarray(pmra_masyr, dtype=float)[ok])
    pmde = np.nan_to_num(np.asarray(pmde_masyr, dtype=float)[ok])
    plx = np.nan_to_num(np.asarray(plx_mas, dtype=float)[ok])
    plx_arcsec = np.clip(plx, 0.0, None) / MAS_PER_ARCSEC

    # ERFA wants dRA/dt, without the cos(Dec) factor, in radians a year.
    mas_to_rad = np.radians(1.0 / MAS_PER_DEG)
    pmr = pmra * mas_to_rad / np.cos(dec_rad)
    pmd = pmde * mas_to_rad

    # No source gives radial velocities, so they are zero, as are the
    # second halves of the two-part Julian Dates.
    ra2, dec2, _pmr2, _pmd2, _px2, _rv2 = erfa.pmsafe(
        ra_rad,
        dec_rad,
        pmr,
        pmd,
        plx_arcsec,
        np.zeros_like(ra_rad),
        epoch_jd,
        0.0,
        J2000_JD,
        0.0,
    )
    out_ra[ok] = np.degrees(ra2) % 360.0
    out_dec[ok] = np.degrees(dec2)
    return out_ra, out_dec


def gliese_b1950_to_icrs(
    ra_b1950: list[str],
    dec_b1950: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Converts Gliese B1950 sexagesimal positions to ICRS degrees.

    The Gliese catalogue lists FK4 positions for equinox and epoch
    B1950.0 as ``"hh mm ss"`` and ``"+dd mm.m"`` strings. This only
    changes the reference frame: the result is still the position at
    epoch B1950.0, to be propagated with the catalogue's proper motion.

    Returns:
        ``(ra, dec)`` arrays in ICRS degrees at epoch B1950.0, with NaN
        for rows where either string is empty.
    """
    ra_out = np.full(len(ra_b1950), np.nan)
    dec_out = np.full(len(dec_b1950), np.nan)
    idx = [
        i
        for i, (r, d) in enumerate(zip(ra_b1950, dec_b1950, strict=True))
        if r.strip() and d.strip()
    ]
    if not idx:
        return ra_out, dec_out
    coords = SkyCoord(
        [ra_b1950[i] for i in idx],
        [dec_b1950[i] for i in idx],
        unit=(u.hourangle, u.deg),
        frame="fk4",
        equinox="B1950",
        obstime="B1950",
    ).icrs
    ra_out[idx] = coords.ra.deg
    dec_out[idx] = coords.dec.deg
    return ra_out, dec_out


def angular_sep_deg(
    ra1: float | None,
    dec1: float | None,
    ra2: float | None,
    dec2: float | None,
) -> float:
    """The angle between two sky positions given in degrees.

    Uses the Vincenty formula, which stays accurate at small angles.

    Returns:
        The separation in degrees, or ``UNKNOWN_SEP_DEG`` when any
        coordinate is ``None``.
    """
    if ra1 is None or dec1 is None or ra2 is None or dec2 is None:
        return UNKNOWN_SEP_DEG
    ra1, dec1, ra2, dec2 = (
        math.radians(ra1),
        math.radians(dec1),
        math.radians(ra2),
        math.radians(dec2),
    )
    sin1, cos1 = math.sin(dec1), math.cos(dec1)
    sin2, cos2 = math.sin(dec2), math.cos(dec2)
    d_ra = ra2 - ra1
    sin_dra, cos_dra = math.sin(d_ra), math.cos(d_ra)
    num = math.sqrt(
        (cos2 * sin_dra) ** 2 + (cos1 * sin2 - sin1 * cos2 * cos_dra) ** 2
    )
    den = sin1 * sin2 + cos1 * cos2 * cos_dra
    return math.degrees(math.atan2(num, den))
