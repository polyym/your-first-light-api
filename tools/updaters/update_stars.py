#!/usr/bin/env python3
"""
update_stars.py — Refresh stars.json from multiple astronomical catalogues.

Queries HIPPARCOS, Gliese Catalogue of Nearby Stars, and Gaia DR3 via Vizier,
plus the NASA Exoplanet Archive for planet counts. Every position is
propagated to epoch J2000.0 from the catalogue's own astrometry before the
catalogues are merged and deduplicated into the most complete nearby star
catalogue possible.

Normally run via the scheduled data-refresh workflow or the single
entry point:

    pip install -e ".[catalogue]"    # one-time
    python tools/update_data.py stars

The write is atomic and only happens when the content changed;
validation failures exit non-zero without touching the data file.
"""

import json
import math
import os
import sys
from pathlib import Path

import erfa
import numpy as np

MAX_RADIUS_LY = 160  # covers anyone up to ~160 years old
MIN_PARALLAX_SNR = 5  # reject stars where Plx / e_Plx < this

# --- Cross-catalogue duplicate detection -----------------------------------
# Matching is two-tier:
#
# Tier 1 (same position): cross-catalogue entries within COINCIDENT_SEP_ARCSEC
# are the same physical star REGARDLESS of how much their distances disagree.
# With ~55k stars on the whole sky the expected number of chance alignments
# this close is well below one, while Gliese photometric parallaxes and
# faint-end HIPPARCOS parallaxes routinely disagree with Gaia by 10-80
# percent, so a distance test here creates duplicates instead of preventing
# them. When either position comes from the Gliese catalogue the radius is
# GLIESE_COINCIDENT_SEP_ARCSEC instead: its positions are quantised to a
# second of time and carry fifty years of proper motion from a catalogue
# whose motions for faint stars are good to a few tenths of an arcsecond per
# year, so the same star routinely lands 15-30 arcsec from its Gaia entry.
# The expected number of chance alignments at 30 arcsec is still below one.
#
# Tier 2 (wide window): between COINCIDENT_SEP_ARCSEC and
# MERGE_MAX_SEP_DEG the distances must also agree within a distance-scaled
# tolerance, because a window this wide contains genuinely unrelated stars.
# Every source is propagated to epoch J2000.0 before matching, so this
# window exists only to absorb the Gliese catalogue's coarse positions (one
# second of time in RA, 0.1 arcmin in Dec, plus fifty years of proper
# motion applied from a PA quoted to 0.1 deg). It never applies between
# two entries whose positions both come from HIPPARCOS or Gaia: at a common
# epoch those agree to well under an arcsecond for the same star, so two
# such positions further apart than tier 1 are two stars, typically a wide
# companion at the same distance (Epsilon Indi A and its brown-dwarf pair,
# 400 arcsec apart, used to be merged this way).
COINCIDENT_SEP_ARCSEC = 15.0
GLIESE_COINCIDENT_SEP_ARCSEC = 30.0
MERGE_MAX_SEP_DEG = 0.15  # 540 arcsec

# Tier 2 distance agreement scales with distance, because parallax
# uncertainty (and hence inter-catalogue disagreement) grows with distance:
# real disagreement of several light-years is normal beyond ~20 ly. A fixed
# 1 ly tolerance is what allowed ~4,000 duplicated stars into the catalogue.
MERGE_DIST_TOL_FRACTION = 0.10
MERGE_DIST_TOL_FLOOR_LY = 1.0

# Validation thresholds: entries closer than DUPLICATE_SEP_ARCSEC on the sky
# whose distances disagree by more than max(FLOOR, FRACTION * distance) are
# flagged as duplicates, unless they are a resolved pair from a single
# catalogue or a hand-curated multiple system. Genuine components agree in
# distance to within a few percent; duplicates disagree by far more.
DUPLICATE_SEP_ARCSEC = 15.0
DUPLICATE_DIST_TOL_FRACTION = 0.05
DUPLICATE_DIST_TOL_FLOOR_LY = 0.5

# Relative reliability of parallaxes per source; on a merge the distance is
# taken from the most reliable contributing catalogue.
_SOURCE_QUALITY = {"gliese": 1, "hipparcos": 2, "gaia": 3}

# Minimum plausible result sizes per upstream fetch, set at roughly half of
# what each source returns today (HIPPARCOS 6.5k, Gliese 3.1k, Gaia 48k rows;
# Exoplanet Archive 5.6k name keys). A fetch below its floor means the source
# failed or silently degraded, and building a catalogue from what remains
# would produce a plausible-looking but incomplete data file, so the run
# refuses to continue instead.
MIN_FETCH_COUNTS = {
    "hipparcos": 3_000,
    "gliese": 1_500,
    "gaia": 20_000,
    "exoplanet_archive": 1_000,
}


def check_fetch_counts(counts: dict[str, int]) -> list[str]:
    """Guard against silently degraded upstream fetches.

    Args:
        counts: Mapping of fetch label (a ``MIN_FETCH_COUNTS``
            key) to the number of rows/keys it returned.

    Returns:
        A list of error messages; empty when every fetch met
        its floor.
    """
    errors = []
    for label, count in counts.items():
        floor = MIN_FETCH_COUNTS[label]
        if count < floor:
            errors.append(
                f"FETCH: {label} returned {count} rows "
                f"(expected >= {floor}); refusing to build "
                f"a degraded catalogue"
            )
    return errors


# ---------------------------------------------------------------------------
# Coordinate epochs
#
# The API publishes ICRS positions at epoch J2000.0. Every source catalogue
# records positions at its own epoch (HIPPARCOS J1991.25, Gaia DR3 J2016.0,
# Gliese B1950.0), and nearby stars move fast enough (Barnard's Star ~10
# arcsec/yr) that the difference amounts to tens to hundreds of arcseconds.
# The updater therefore reads each catalogue's native position and proper
# motion columns and propagates them to J2000.0 itself, instead of relying
# on VizieR's computed _RAJ2000/_DEJ2000 columns. In 2026 VizieR silently
# stopped applying proper motion to those columns for the Gliese catalogue,
# which shifted every fast-moving Gliese star by decades of motion, broke
# the cross-catalogue match and duplicated ~300 nearby stars in one refresh
# without tripping a single check.
# ---------------------------------------------------------------------------
J2000_JD = 2451545.0
B1950_JD = 2433282.4235  # Besselian epoch B1950.0
HIPPARCOS_EPOCH_JD = J2000_JD + (1991.25 - 2000.0) * 365.25
GAIA_DR3_EPOCH_JD = J2000_JD + (2016.0 - 2000.0) * 365.25


def propagate_to_j2000(
    ra_deg: np.ndarray,
    dec_deg: np.ndarray,
    pmra_masyr: np.ndarray,
    pmde_masyr: np.ndarray,
    plx_mas: np.ndarray,
    epoch_jd: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Move ICRS positions from a catalogue epoch to J2000.0.

    Uses ERFA's rigorous space-motion propagation (``pmsafe``),
    vectorised over the whole catalogue. Missing proper motions
    count as zero; rows with no usable position come back as NaN.

    Args:
        ra_deg: Right ascension at ``epoch_jd`` (degrees).
        dec_deg: Declination at ``epoch_jd`` (degrees).
        pmra_masyr: Proper motion in RA including the cos(Dec)
            factor, as catalogues publish it (mas/yr).
        pmde_masyr: Proper motion in Dec (mas/yr).
        plx_mas: Parallax (mas); only affects the tiny
            perspective term, so a NaN is treated as zero.
        epoch_jd: Julian Date of the catalogue epoch.

    Returns:
        ``(ra, dec)`` arrays in degrees at epoch J2000.0, with RA
        normalised to ``[0, 360)``.
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
    plx_arcsec = np.clip(plx, 0.0, None) / 1000.0

    # ERFA wants dRA/dt (not multiplied by cos Dec) in radians/yr.
    mas_to_rad = np.radians(1.0 / 3.6e6)
    pmr = pmra * mas_to_rad / np.cos(dec_rad)
    pmd = pmde * mas_to_rad

    ra2, dec2, _pmr2, _pmd2, _px2, _rv2 = erfa.pmsafe(
        ra_rad, dec_rad, pmr, pmd, plx_arcsec, np.zeros_like(ra_rad),
        epoch_jd, 0.0, J2000_JD, 0.0,
    )
    out_ra[ok] = np.degrees(ra2) % 360.0
    out_dec[ok] = np.degrees(dec2)
    return out_ra, out_dec


def gliese_b1950_to_icrs(
    ra_b1950: list[str],
    dec_b1950: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Convert Gliese B1950 sexagesimal positions to ICRS degrees.

    The Gliese catalogue lists FK4 positions for equinox and epoch
    B1950.0 as ``"hh mm ss"`` and ``"+dd mm.m"`` strings. This
    only changes the reference frame; the result is still the
    position at epoch B1950.0 and must be propagated with the
    catalogue's proper motion afterwards.

    Args:
        ra_b1950: RA strings; empty strings give NaN.
        dec_b1950: Dec strings; empty strings give NaN.

    Returns:
        ``(ra, dec)`` arrays in ICRS degrees at epoch B1950.0.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    ra_out = np.full(len(ra_b1950), np.nan)
    dec_out = np.full(len(dec_b1950), np.nan)
    idx = [
        i for i, (r, d) in enumerate(zip(ra_b1950, dec_b1950))
        if r.strip() and d.strip()
    ]
    if not idx:
        return ra_out, dec_out
    coords = SkyCoord(
        [ra_b1950[i] for i in idx],
        [dec_b1950[i] for i in idx],
        unit=(u.hourangle, u.deg),
        frame="fk4", equinox="B1950", obstime="B1950",
    ).icrs
    ra_out[idx] = coords.ra.deg
    dec_out[idx] = coords.dec.deg
    return ra_out, dec_out


def _float_column(table, name: str) -> np.ndarray:
    """A table column as a float array with masked cells as NaN."""
    return np.ma.filled(np.ma.asarray(table[name], dtype=float), np.nan)


def _text_cell(value) -> str:
    """A table cell as stripped text, masked cells as ``""``."""
    if np.ma.is_masked(value):
        return ""
    return " ".join(str(value).split())


# ICRS J2000.0 positions (SIMBAD) of fast-moving stars that every source
# must return within REFERENCE_MAX_SEP_ARCSEC of these values, keyed by the
# catalogue's own identifier. A fetch whose coordinates come back at the
# wrong epoch, in different units or from a different column puts these
# stars tens to hundreds of arcseconds away, so the run refuses to build a
# catalogue from it. The tolerance covers the Gliese catalogue's coarse
# position precision (one second of time in RA, 0.1 arcmin in Dec).
REFERENCE_POSITIONS: dict[str, dict[str, tuple[float, float]]] = {
    "hipparcos": {
        "87937": (269.45208, 4.69336),   # Barnard's Star
        "57939": (178.24487, 37.71868),  # Groombridge 1830
        "24186": (77.91912, -45.01843),  # Kapteyn's Star
    },
    "gliese": {
        "Gl 699": (269.45208, 4.69336),
        "Gl 451 A": (178.24487, 37.71868),
        "Gl 191": (77.91912, -45.01843),
    },
    "gaia": {
        "4472832130942575872": (269.45208, 4.69336),
        "4034171629042489088": (178.24487, 37.71868),
        "4810594479418041856": (77.91912, -45.01843),
    },
}
REFERENCE_MAX_SEP_ARCSEC = 20.0


def check_reference_positions(stars: list[dict], source: str) -> list[str]:
    """Guard against a fetch whose positions are at the wrong epoch.

    Args:
        stars: Star dicts from one fetcher; each carries the
            catalogue's own identifier in ``_catalogue_id``.
        source: ``REFERENCE_POSITIONS`` key naming the fetcher.

    Returns:
        A list of error messages; empty when every reference star
        was returned close to its known J2000.0 position.
    """
    by_id = {s.get("_catalogue_id"): s for s in stars}
    errors = []
    for cid, (ra, dec) in REFERENCE_POSITIONS[source].items():
        star = by_id.get(cid)
        if star is None:
            errors.append(
                f"REFERENCE: {source} did not return {cid}; "
                f"refusing to build a catalogue from a fetch "
                f"missing a well-known nearby star"
            )
            continue
        sep_arcsec = _angular_sep_deg(
            star.get("ra_deg"), star.get("dec_deg"), ra, dec,
        ) * 3600.0
        if sep_arcsec > REFERENCE_MAX_SEP_ARCSEC:
            errors.append(
                f"REFERENCE: {source} places {cid} "
                f"{sep_arcsec:.0f} arcsec from its J2000 position "
                f"(limit {REFERENCE_MAX_SEP_ARCSEC:.0f}); the "
                f"fetch is probably at the wrong epoch"
            )
    return errors


def _distance_tolerance_ly(distance_ly: float) -> float:
    """Tier 2 distance disagreement allowed for one star."""
    return max(
        MERGE_DIST_TOL_FLOOR_LY,
        MERGE_DIST_TOL_FRACTION * distance_ly,
    )


def _sources(s: dict) -> set[str]:
    """Every catalogue this (possibly merged) entry drew from.

    Args:
        s: Star dict, before or after merging/writing.

    Returns:
        Set of source names; empty for hand-curated entries.
    """
    merged = s.get("_merged_sources")
    if merged:
        return merged
    listed = s.get("sources")
    if listed:
        return set(listed)
    src = s.get("_source") or s.get("source")
    return {src} if src else set()


# ---------------------------------------------------------------------------
# Common names for well-known nearby stars (by HIP ID)
#
# Every mapping was re-verified against SIMBAD on 2026-09-06 by comparing
# the HIPPARCOS position of the ID with SIMBAD's position for the name.
# Eight of the previous mappings pointed at the wrong star (for example
# HIP 49908 is Groombridge 1618, not Wolf 359, and HIP 91768/91772 are
# Struve 2398 A/B, not Kruger 60 A/B). A wrong mapping renames a real star
# and, when the name also has a KNOWN_STAR_OVERRIDES entry, overwrites that
# star's data with another star's, so the real star vanishes and the named
# star is counted twice. Do NOT add HIP IDs without confirming the
# cross-match; the OVERRIDE_MISMATCH validation check fails the run when
# an override lands on an entry whose catalogue position is somewhere else.
# ---------------------------------------------------------------------------
HIP_COMMON_NAMES = {
    70890: "Proxima Centauri",
    71683: "Alpha Centauri A",
    71681: "Alpha Centauri B",
    87937: "Barnard's Star",
    32349: "Sirius A",
    # Sirius B is not resolved in HIPPARCOS — see EXTRA_STARS
    16537: "Epsilon Eridani",
    8102: "Tau Ceti",
    37279: "Procyon A",
    36208: "Luyten's Star",
    54035: "Lalande 21185",
    88601: "70 Ophiuchi A",
    104214: "61 Cygni A",
    104217: "61 Cygni B",
    57548: "Ross 128",
    114046: "Lacaille 9352",
    92403: "Ross 154",
    # Ross 248 and Wolf 359 are too faint for HIPPARCOS; they enter
    # through the Gliese catalogue (Gl 905 and Gl 406).
    97649: "Altair",
    91262: "Vega",
    113368: "Fomalhaut",
    49908: "Groombridge 1618",
    80824: "Wolf 1061",
    108870: "Epsilon Indi A",
    96100: "Sigma Draconis",
    99240: "Delta Pavonis",
    15510: "82 Eridani",
    37826: "Pollux",
    69673: "Arcturus",
    3829: "Van Maanen's Star",
    1475: "Groombridge 34 A",
    # Groombridge 34 B has no HIPPARCOS entry — see EXTRA_STARS
    110893: "Kruger 60 A",
    91768: "Struve 2398 A",
    91772: "Struve 2398 B",
    105090: "Lacaille 8760",
    24186: "Kapteyn's Star",
    84405: "36 Ophiuchi A",
    84478: "36 Ophiuchi C",
    5643: "YZ Ceti",
    93873: "GJ 745 A",
    93899: "GJ 745 B",
    106440: "GJ 832",
}

# Gliese catalogue name mappings, keyed by the designation ``gliese_name``
# builds from the catalogue name and component letter (e.g. "Gl 559 A").
# Verified against SIMBAD on 2026-09-06. Names that also appear in
# HIP_COMMON_NAMES, KNOWN_STAR_OVERRIDES or EXTRA_STARS make the Gliese
# row merge with (or be replaced by) that entry instead of surviving as a
# second copy of the same star under its Gliese designation.
GLIESE_COMMON_NAMES = {
    "Gl 551": "Proxima Centauri",
    "Gl 559 A": "Alpha Centauri A", "Gl 559 B": "Alpha Centauri B",
    "Gl 699": "Barnard's Star",
    "Gl 406": "Wolf 359",
    "Gl 411": "Lalande 21185",
    "Gl 244 A": "Sirius A", "Gl 244 B": "Sirius B",
    "Gl 65 A": "Luyten 726-8A (BL Ceti)",
    "Gl 65 B": "Luyten 726-8B (UV Ceti)",
    "Gl 729": "Ross 154",
    "Gl 905": "Ross 248",
    "Gl 144": "Epsilon Eridani",
    "Gl 887": "Lacaille 9352",
    "Gl 447": "Ross 128",
    "Gl 866 AB": "EZ Aquarii A",  # unresolved triple in the catalogue
    "Gl 280 A": "Procyon A", "Gl 280 B": "Procyon B",
    "Gl 820 A": "61 Cygni A", "Gl 820 B": "61 Cygni B",
    "Gl 725 A": "Struve 2398 A", "Gl 725 B": "Struve 2398 B",
    "Gl 15 A": "Groombridge 34 A", "Gl 15 B": "Groombridge 34 B",
    "Gl 845": "Epsilon Indi A",
    "GJ 1111": "DX Cancri",
    "Gl 71": "Tau Ceti",
    "Gl 54.1": "YZ Ceti",
    "Gl 273": "Luyten's Star",
    "Gl 191": "Kapteyn's Star",
    "Gl 825": "Lacaille 8760",
    "Gl 860 A": "Kruger 60 A", "Gl 860 B": "Kruger 60 B",
    "Gl 83.1": "TZ Arietis",
    "Gl 35": "Van Maanen's Star",
    "Gl 628": "Wolf 1061",
    "Gl 380": "Groombridge 1618",
    "Gl 702 A": "70 Ophiuchi A", "Gl 702 B": "70 Ophiuchi B",
    "Gl 663 A": "36 Ophiuchi A", "Gl 663 B": "36 Ophiuchi B",
    "Gl 764": "Sigma Draconis",
    "Gl 780": "Delta Pavonis",
    "Gl 139": "82 Eridani",
    "Gl 768": "Altair",
    "Gl 721": "Vega",
    "Gl 881": "Fomalhaut",
    "Gl 286": "Pollux",
    "Gl 541": "Arcturus",
    "Gl 687": "GJ 687",
    "Gl 674": "GJ 674",
    "Gl 876": "GJ 876",
    "Gl 832": "GJ 832",
    "Gl 581": "GJ 581",
    "Gl 667 C": "GJ 667 C",
    "Gl 251": "GJ 251",
    "Gl 436": "GJ 436",
    "Gl 745 A": "GJ 745 A", "Gl 745 B": "GJ 745 B",
    "GJ 1061": "GJ 1061",
    "GJ 1002": "GJ 1002",
    "GJ 1214": "GJ 1214",
    "NN 3323": "GJ 3323",  # CNS3 provisional number; GJ 3323 hosts 2 planets
}


# ---------------------------------------------------------------------------
# Hand-verified override data for the most important nearby stars.
# Applied AFTER all catalogue merging to correct any bad data.
# Source: SIMBAD, NASA Exoplanet Archive (2024 data). Coordinates are
# SIMBAD ICRS J2000.0 positions, re-checked on 2026-09-06 (several were
# wrong by degrees, which also broke the duplicate removal that relies on
# them). The catalogue entry an override lands on must sit within
# OVERRIDE_MAX_SEP_ARCSEC of these coordinates, or validation fails.
# ---------------------------------------------------------------------------
OVERRIDE_MAX_SEP_ARCSEC = 60.0

KNOWN_STAR_OVERRIDES: dict[str, dict] = {
    "Proxima Centauri": {
        "distance_ly": 4.2465, "spectral_type": "M5.5Ve",
        "apparent_magnitude": 11.13, "known_exoplanets": 3,
        "ra_deg": 217.4289, "dec_deg": -62.6795,
    },
    "Alpha Centauri A": {
        "distance_ly": 4.3650, "spectral_type": "G2V",
        "apparent_magnitude": -0.01, "known_exoplanets": 0,
        "ra_deg": 219.9021, "dec_deg": -60.8340,
    },
    "Alpha Centauri B": {
        "distance_ly": 4.3650, "spectral_type": "K1V",
        "apparent_magnitude": 1.35, "known_exoplanets": 0,
        "ra_deg": 219.8961, "dec_deg": -60.8375,
    },
    "Barnard's Star": {
        "distance_ly": 5.9577, "spectral_type": "M4.0V",
        "apparent_magnitude": 9.51, "known_exoplanets": 1,
        "ra_deg": 269.4521, "dec_deg": 4.6934,
    },
    "Wolf 359": {
        "distance_ly": 7.8558, "spectral_type": "M6.5Ve",
        "apparent_magnitude": 13.54, "known_exoplanets": 0,
        "ra_deg": 164.1205, "dec_deg": 7.0147,
    },
    "Lalande 21185": {
        "distance_ly": 8.3044, "spectral_type": "M2.0V",
        "apparent_magnitude": 7.52, "known_exoplanets": 2,
        "ra_deg": 165.8341, "dec_deg": 35.9699,
    },
    "Sirius A": {
        "distance_ly": 8.6094, "spectral_type": "A1V",
        "apparent_magnitude": -1.46, "known_exoplanets": 0,
        "ra_deg": 101.2872, "dec_deg": -16.7161,
    },
    "Ross 154": {
        "distance_ly": 9.6813, "spectral_type": "M3.5Ve",
        "apparent_magnitude": 10.44, "known_exoplanets": 0,
        "ra_deg": 282.4557, "dec_deg": -23.8362,
    },
    "Ross 248": {
        "distance_ly": 10.2903, "spectral_type": "M5.5V",
        "apparent_magnitude": 12.29, "known_exoplanets": 0,
        "ra_deg": 355.4793, "dec_deg": 44.1774,
    },
    "Epsilon Eridani": {
        "distance_ly": 10.475, "spectral_type": "K2V",
        "apparent_magnitude": 3.73, "known_exoplanets": 1,
        "ra_deg": 53.2327, "dec_deg": -9.4583,
    },
    "Lacaille 9352": {
        "distance_ly": 10.721, "spectral_type": "M0.5V",
        "apparent_magnitude": 7.34, "known_exoplanets": 2,
        "ra_deg": 346.4668, "dec_deg": -35.8531,
    },
    "Ross 128": {
        "distance_ly": 11.007, "spectral_type": "M4.0V",
        "apparent_magnitude": 11.13, "known_exoplanets": 1,
        "ra_deg": 176.9350, "dec_deg": 0.8046,
    },
    "61 Cygni A": {
        "distance_ly": 11.403, "spectral_type": "K5V",
        "apparent_magnitude": 5.21, "known_exoplanets": 0,
        "ra_deg": 316.7247, "dec_deg": 38.7494,
    },
    "61 Cygni B": {
        "distance_ly": 11.403, "spectral_type": "K7V",
        "apparent_magnitude": 6.03, "known_exoplanets": 0,
        "ra_deg": 316.7303, "dec_deg": 38.7420,
    },
    "Procyon A": {
        "distance_ly": 11.402, "spectral_type": "F5IV-V",
        "apparent_magnitude": 0.37, "known_exoplanets": 0,
        "ra_deg": 114.8255, "dec_deg": 5.2250,
    },
    "Groombridge 34 A": {
        "distance_ly": 11.624, "spectral_type": "M1.5V",
        "apparent_magnitude": 8.08, "known_exoplanets": 0,
        "ra_deg": 4.5954, "dec_deg": 44.0230,
    },
    "Tau Ceti": {
        "distance_ly": 11.912, "spectral_type": "G8.5V",
        "apparent_magnitude": 3.50, "known_exoplanets": 4,
        "ra_deg": 26.0170, "dec_deg": -15.9375,
    },
    "Epsilon Indi A": {
        "distance_ly": 11.869, "spectral_type": "K5V",
        "apparent_magnitude": 4.69, "known_exoplanets": 1,
        "ra_deg": 330.8402, "dec_deg": -56.7860,
    },
    "Luyten's Star": {
        "distance_ly": 12.366, "spectral_type": "M3.5V",
        "apparent_magnitude": 9.87, "known_exoplanets": 2,
        "ra_deg": 111.8521, "dec_deg": 5.2258,
    },
    "YZ Ceti": {
        "distance_ly": 12.132, "spectral_type": "M4.5V",
        "apparent_magnitude": 12.07, "known_exoplanets": 3,
        "ra_deg": 18.1277, "dec_deg": -16.9990,
    },
    "Kapteyn's Star": {
        "distance_ly": 12.777, "spectral_type": "sdM1",
        "apparent_magnitude": 8.85, "known_exoplanets": 2,
        "ra_deg": 77.9191, "dec_deg": -45.0184,
    },
    "Kruger 60 A": {
        "distance_ly": 13.149, "spectral_type": "M3V",
        "apparent_magnitude": 9.79, "known_exoplanets": 0,
        "ra_deg": 336.9982, "dec_deg": 57.6950,
    },
    "Kruger 60 B": {
        "distance_ly": 13.149, "spectral_type": "M4V",
        "apparent_magnitude": 11.41, "known_exoplanets": 0,
        "ra_deg": 336.9991, "dec_deg": 57.6972,
    },
    "70 Ophiuchi A": {
        "distance_ly": 16.592, "spectral_type": "K0V",
        "apparent_magnitude": 4.03, "known_exoplanets": 0,
        "ra_deg": 271.3635, "dec_deg": 2.5001,
    },
    "Sigma Draconis": {
        "distance_ly": 18.798, "spectral_type": "G9V",
        "apparent_magnitude": 4.67, "known_exoplanets": 0,
        "ra_deg": 293.0900, "dec_deg": 69.6612,
    },
    "Delta Pavonis": {
        "distance_ly": 19.893, "spectral_type": "G8IV",
        "apparent_magnitude": 3.56, "known_exoplanets": 0,
        "ra_deg": 302.1817, "dec_deg": -66.1821,
    },
    "Altair": {
        "distance_ly": 16.730, "spectral_type": "A7V",
        "apparent_magnitude": 0.76, "known_exoplanets": 0,
        "ra_deg": 297.6958, "dec_deg": 8.8683,
    },
    "Vega": {
        "distance_ly": 25.040, "spectral_type": "A0V",
        "apparent_magnitude": 0.03, "known_exoplanets": 0,
        "ra_deg": 279.2347, "dec_deg": 38.7837,
    },
    "Fomalhaut": {
        "distance_ly": 25.130, "spectral_type": "A3V",
        "apparent_magnitude": 1.16, "known_exoplanets": 0,
        "ra_deg": 344.4127, "dec_deg": -29.6222,
    },
    "Pollux": {
        "distance_ly": 33.720, "spectral_type": "K0IIIb",
        "apparent_magnitude": 1.14, "known_exoplanets": 1,
        "ra_deg": 116.3290, "dec_deg": 28.0262,
    },
    "Arcturus": {
        "distance_ly": 36.660, "spectral_type": "K1.5III",
        "apparent_magnitude": -0.05, "known_exoplanets": 0,
        "ra_deg": 213.9153, "dec_deg": 19.1824,
    },
}


# ---------------------------------------------------------------------------
# Sub-stellar objects and stars too faint or unresolved for catalogue queries.
# These are hand-verified and ALWAYS override catalogue entries with the same
# name (see main() logic). Coordinates are SIMBAD ICRS J2000.0 positions,
# re-checked on 2026-09-06: dedup_by_coordinates removes catalogue entries
# near these positions, so a wrong coordinate here leaves the star listed
# twice (once curated, once under its Gaia or Gliese designation).
# ---------------------------------------------------------------------------
EXTRA_STARS = [
    # Brown dwarfs / sub-stellar
    {"name": "Luhman 16A", "distance_ly": 6.50, "spectral_type": "L7.5", "apparent_magnitude": 23.25, "known_exoplanets": 0, "ra_deg": 162.3084, "dec_deg": -53.3181},
    {"name": "Luhman 16B", "distance_ly": 6.50, "spectral_type": "T0.5", "apparent_magnitude": 24.07, "known_exoplanets": 0, "ra_deg": 162.3086, "dec_deg": -53.3183},
    {"name": "WISE 0855-0714", "distance_ly": 7.43, "spectral_type": "Y4", "apparent_magnitude": 25.0, "known_exoplanets": 0, "ra_deg": 133.8189, "dec_deg": -7.2470},
    {"name": "WISE 1506+7027", "distance_ly": 11.09, "spectral_type": "T6", "apparent_magnitude": 22.0, "known_exoplanets": 0, "ra_deg": 226.7185, "dec_deg": 70.4570},
    {"name": "WISE 0350-5658", "distance_ly": 11.47, "spectral_type": "Y1", "apparent_magnitude": 24.0, "known_exoplanets": 0, "ra_deg": 57.5025, "dec_deg": -56.9734},
    {"name": "UGPS 0722-0540", "distance_ly": 13.43, "spectral_type": "T9", "apparent_magnitude": 23.8, "known_exoplanets": 0, "ra_deg": 110.6163, "dec_deg": -5.6760},
    {"name": "LP 944-20", "distance_ly": 16.33, "spectral_type": "M9.0V", "apparent_magnitude": 18.50, "known_exoplanets": 0, "ra_deg": 54.8969, "dec_deg": -35.4288},
    {"name": "WISE 1541-2250", "distance_ly": 18.60, "spectral_type": "Y0.5", "apparent_magnitude": 24.5, "known_exoplanets": 0, "ra_deg": 235.4679, "dec_deg": -22.8402},
    {"name": "2MASS J0415-0935", "distance_ly": 18.65, "spectral_type": "T8", "apparent_magnitude": 22.0, "known_exoplanets": 0, "ra_deg": 63.8314, "dec_deg": -9.5852},
    # Stars missing from or unresolved in HIPPARCOS/Gliese/Gaia queries
    {"name": "Luyten 726-8A (BL Ceti)", "distance_ly": 8.728, "spectral_type": "M5.5Ve", "apparent_magnitude": 12.54, "known_exoplanets": 0, "ra_deg": 24.7557, "dec_deg": -17.9507},
    {"name": "Luyten 726-8B (UV Ceti)", "distance_ly": 8.728, "spectral_type": "M6.0Ve", "apparent_magnitude": 12.95, "known_exoplanets": 0, "ra_deg": 24.7568, "dec_deg": -17.9503},
    {"name": "Sirius B", "distance_ly": 8.6094, "spectral_type": "DA2", "apparent_magnitude": 8.44, "known_exoplanets": 0, "ra_deg": 101.2888, "dec_deg": -16.7169},
    {"name": "EZ Aquarii A", "distance_ly": 11.266, "spectral_type": "M5.0V", "apparent_magnitude": 13.33, "known_exoplanets": 0, "ra_deg": 339.6399, "dec_deg": -15.2999},
    {"name": "EZ Aquarii B", "distance_ly": 11.266, "spectral_type": "M5.5V", "apparent_magnitude": 13.27, "known_exoplanets": 0, "ra_deg": 339.6399, "dec_deg": -15.2999},
    {"name": "EZ Aquarii C", "distance_ly": 11.266, "spectral_type": "M6.5V", "apparent_magnitude": 14.03, "known_exoplanets": 0, "ra_deg": 339.6399, "dec_deg": -15.2999},
    {"name": "Struve 2398 A", "distance_ly": 11.525, "spectral_type": "M3.0V", "apparent_magnitude": 8.94, "known_exoplanets": 0, "ra_deg": 280.6946, "dec_deg": 59.6304},
    {"name": "Struve 2398 B", "distance_ly": 11.525, "spectral_type": "M3.5V", "apparent_magnitude": 9.70, "known_exoplanets": 0, "ra_deg": 280.6954, "dec_deg": 59.6269},
    {"name": "Groombridge 34 B", "distance_ly": 11.624, "spectral_type": "M3.5V", "apparent_magnitude": 11.06, "known_exoplanets": 0, "ra_deg": 4.6076, "dec_deg": 44.0272},
    {"name": "GJ 1061", "distance_ly": 11.991, "spectral_type": "M5.5V", "apparent_magnitude": 13.09, "known_exoplanets": 3, "ra_deg": 53.9987, "dec_deg": -44.5127},
    {"name": "DX Cancri", "distance_ly": 11.826, "spectral_type": "M6.5Ve", "apparent_magnitude": 14.78, "known_exoplanets": 0, "ra_deg": 127.4556, "dec_deg": 26.7760},
    # NOTE: "SO 0253+1652" is Teegarden's Star's discovery
    # designation and must not be listed as a separate entry.
    {"name": "Teegarden's Star", "distance_ly": 12.497, "spectral_type": "M7.0V", "apparent_magnitude": 15.40, "known_exoplanets": 2, "ra_deg": 43.2537, "dec_deg": 16.8813},
    {"name": "SCR 1845-6357 A", "distance_ly": 12.57, "spectral_type": "M8.5V", "apparent_magnitude": 17.39, "known_exoplanets": 0, "ra_deg": 281.2719, "dec_deg": -63.9632},
    {"name": "DENIS J1048-3956", "distance_ly": 13.17, "spectral_type": "M8.5V", "apparent_magnitude": 17.39, "known_exoplanets": 0, "ra_deg": 162.0607, "dec_deg": -39.9352},
    {"name": "SCR J1546-5534", "distance_ly": 14.10, "spectral_type": "M8.5V", "apparent_magnitude": 17.30, "known_exoplanets": 0, "ra_deg": 236.6737, "dec_deg": -55.5799},
    {"name": "GJ 876", "distance_ly": 15.238, "spectral_type": "M4.0V", "apparent_magnitude": 10.17, "known_exoplanets": 4, "ra_deg": 343.3197, "dec_deg": -14.2637},
    {"name": "GJ 832", "distance_ly": 16.085, "spectral_type": "M1.5V", "apparent_magnitude": 8.66, "known_exoplanets": 2, "ra_deg": 323.3916, "dec_deg": -49.0090},
    {"name": "TRAPPIST-1", "distance_ly": 40.66, "spectral_type": "M8V", "apparent_magnitude": 18.80, "known_exoplanets": 7, "ra_deg": 346.6224, "dec_deg": -5.0414},
    {"name": "LP 890-9", "distance_ly": 104.9, "spectral_type": "M6V", "apparent_magnitude": 18.12, "known_exoplanets": 2, "ra_deg": 64.1298, "dec_deg": -28.3147},
]


# ---------------------------------------------------------------------------
# Catalogue fetchers
#
# Each fetcher asks VizieR for the catalogue's native position, proper
# motion and parallax columns and derives J2000.0 positions itself (see the
# coordinate-epoch section above). Every returned star carries the
# catalogue's own identifier in ``_catalogue_id`` for the reference check.
# ---------------------------------------------------------------------------
def fetch_hipparcos(max_dist_ly: float) -> list[dict]:
    """Query HIPPARCOS via Vizier for stars within *max_dist_ly*.

    Filters by parallax signal-to-noise ratio to reject entries
    with unreliable distance measurements. Positions are the
    catalogue's ICRS values at epoch J1991.25 propagated to
    J2000.0 with the catalogue proper motions.

    Args:
        max_dist_ly: Maximum distance in light-years.

    Returns:
        A list of star dicts with keys ``name``, ``distance_ly``,
        ``spectral_type``, ``apparent_magnitude``,
        ``known_exoplanets``, ``ra_deg``, ``dec_deg``,
        ``_source``, ``_catalogue_id`` and ``_hip_id``.
    """
    from astroquery.vizier import Vizier

    max_dist_pc = max_dist_ly / 3.26156
    min_parallax = 1000.0 / max_dist_pc

    print(f"[1/4] Querying HIPPARCOS (parallax > {min_parallax:.1f} mas)...")
    v = Vizier(
        columns=["HIP", "RAICRS", "DEICRS", "pmRA", "pmDE", "Plx", "e_Plx", "Vmag", "SpType"],
        row_limit=-1,
    )
    try:
        result = v.query_constraints(catalog="I/239/hip_main", Plx=f">{min_parallax:.1f}")
    except Exception as e:
        print(f"  WARNING: HIPPARCOS query failed: {e}")
        return []

    if not result or len(result) == 0:
        print("  WARNING: No HIPPARCOS results")
        return []

    table = result[0]
    ra_j2000, dec_j2000 = propagate_to_j2000(
        _float_column(table, "RAICRS"), _float_column(table, "DEICRS"),
        _float_column(table, "pmRA"), _float_column(table, "pmDE"),
        _float_column(table, "Plx"), HIPPARCOS_EPOCH_JD,
    )

    stars = []
    for i, row in enumerate(table):
        try:
            plx = float(row["Plx"])
        except (ValueError, TypeError):
            continue
        if plx <= 0:
            continue
        try:
            e_plx = float(row["e_Plx"])
        except (ValueError, TypeError):
            continue  # skip stars with unparseable parallax errors
        if e_plx > 0 and plx / e_plx < MIN_PARALLAX_SNR:
            continue
        dist_ly = (1000.0 / plx) * 3.26156
        vmag = float(row["Vmag"]) if not np.ma.is_masked(row["Vmag"]) else 99.0
        sp = _text_cell(row["SpType"])
        hip_id = int(row["HIP"])
        name = HIP_COMMON_NAMES.get(hip_id, f"HIP {hip_id}")

        ra, dec = ra_j2000[i], dec_j2000[i]
        has_pos = bool(np.isfinite(ra) and np.isfinite(dec))

        stars.append({
            "name": name,
            "distance_ly": round(dist_ly, 4),
            "spectral_type": sp,
            "apparent_magnitude": round(vmag, 2),
            "magnitude_band": "V",
            "known_exoplanets": 0,
            "ra_deg": round(float(ra), 4) if has_pos else None,
            "dec_deg": round(float(dec), 4) if has_pos else None,
            "_source": "hipparcos",
            "_pos_source": "hipparcos",
            "_catalogue_id": str(hip_id),
            "_hip_id": hip_id,
        })

    print(f"  Found {len(stars)} stars")
    return stars


def gliese_name(name: str, comp: str) -> str:
    """Build the designation for one Gliese catalogue row.

    The catalogue lists resolved multiple systems as one row per
    component, with the component letter in a separate column.
    ``(Name, Comp)`` is unique across the table while ``Name``
    alone is not (Gl 451 A and B, Gl 4 A and B, ...), so the
    component is part of the designation, e.g. ``"Gl 559 A"``.

    Args:
        name: Raw ``Name`` cell, e.g. ``"Gl 559"``.
        comp: Raw ``Comp`` cell, e.g. ``"A"`` or ``""``.

    Returns:
        The designation with single spaces.
    """
    return " ".join(f"{name} {comp}".split())


def fetch_gliese(max_dist_ly: float) -> list[dict]:
    """Query the Gliese Catalogue of Nearby Stars (3rd ed.) via Vizier.

    Positions are the catalogue's B1950 values converted to ICRS
    and propagated from epoch B1950.0 to J2000.0 with the
    catalogue's total proper motion and position angle.

    Args:
        max_dist_ly: Maximum distance in light-years.

    Returns:
        A list of star dicts with the same schema as
        ``fetch_hipparcos`` (minus ``_hip_id``).
    """
    from astroquery.vizier import Vizier

    max_dist_pc = max_dist_ly / 3.26156
    min_parallax = 1000.0 / max_dist_pc

    print("[2/4] Querying Gliese Catalogue of Nearby Stars...")
    v = Vizier(
        columns=["Name", "Comp", "RAB1950", "DEB1950", "pm", "pmPA", "plx", "e_plx", "Vmag", "Sp"],
        row_limit=-1,
    )
    try:
        result = v.query_constraints(catalog="V/70A/catalog", plx=f">{min_parallax:.1f}")
    except Exception as e:
        print(f"  WARNING: Gliese query failed: {e}")
        return []

    if not result or len(result) == 0:
        print("  WARNING: No Gliese results")
        return []

    table = result[0]
    ra_1950, dec_1950 = gliese_b1950_to_icrs(
        [_text_cell(x) for x in table["RAB1950"]],
        [_text_cell(x) for x in table["DEB1950"]],
    )
    pm_arcsec = np.nan_to_num(_float_column(table, "pm"))
    pa_rad = np.radians(np.nan_to_num(_float_column(table, "pmPA")))
    ra_j2000, dec_j2000 = propagate_to_j2000(
        ra_1950, dec_1950,
        pm_arcsec * 1000.0 * np.sin(pa_rad),
        pm_arcsec * 1000.0 * np.cos(pa_rad),
        _float_column(table, "plx"), B1950_JD,
    )

    stars = []
    for i, row in enumerate(table):
        try:
            plx = float(row["plx"])
        except (ValueError, TypeError):
            continue
        if plx <= 0:
            continue
        try:
            e_plx = float(row["e_plx"])
        except (ValueError, TypeError):
            continue  # skip stars with unparseable parallax errors
        if e_plx > 0 and plx / e_plx < MIN_PARALLAX_SNR:
            continue
        dist_ly = (1000.0 / plx) * 3.26156
        vmag = float(row["Vmag"]) if not np.ma.is_masked(row["Vmag"]) else 99.0
        sp = _text_cell(row["Sp"])
        raw_name = gliese_name(_text_cell(row["Name"]), _text_cell(row["Comp"]))

        # Apply common name if known
        name = GLIESE_COMMON_NAMES.get(raw_name, raw_name)

        ra, dec = ra_j2000[i], dec_j2000[i]
        has_pos = bool(np.isfinite(ra) and np.isfinite(dec))

        stars.append({
            "name": name,
            "distance_ly": round(dist_ly, 4),
            "spectral_type": sp,
            "apparent_magnitude": round(vmag, 2),
            "magnitude_band": "V",
            "known_exoplanets": 0,
            "ra_deg": round(float(ra), 4) if has_pos else None,
            "dec_deg": round(float(dec), 4) if has_pos else None,
            "_source": "gliese",
            "_pos_source": "gliese",
            "_catalogue_id": raw_name,
        })

    print(f"  Found {len(stars)} stars")
    return stars


def gaia_g_to_v(gmag: float, bp_rp: float | None) -> float | None:
    """Approximate Johnson V from Gaia DR3 G using BP-RP colour.

    Uses the Gaia DR3 photometric relationship (Riello et al.
    2021): ``G - V = -0.02704 + 0.01424x - 0.2156x^2 +
    0.01426x^3`` with ``x = BP-RP``, valid for -0.5 < x < 5.0.
    For red stars G can be up to ~1.5 mag brighter than V, so
    storing raw G in a V-band field inflates naked-eye counts.

    Args:
        gmag: Gaia broad-band G magnitude.
        bp_rp: Gaia BP-RP colour, or ``None`` when unavailable.

    Returns:
        Estimated V magnitude, or ``None`` when the colour is
        missing or outside the relation's validity range.
    """
    if bp_rp is None or not (-0.5 < bp_rp < 5.0):
        return None
    g_minus_v = (
        -0.02704
        + 0.01424 * bp_rp
        - 0.2156 * bp_rp**2
        + 0.01426 * bp_rp**3
    )
    return gmag - g_minus_v


def estimate_spectral_class(
    bp_rp: float | None,
    gmag: float,
    dist_ly: float,
) -> str:
    """Estimate a coarse spectral class from Gaia colour.

    Main-sequence boundaries follow the Pecaut & Mamajek (2013)
    BP-RP colour table; blue objects far too faint for the main
    sequence at their measured distance are white dwarfs. The
    result carries an ``(est)`` marker so estimated classes are
    always distinguishable from catalogue MK types; the API's
    ``classify_spectral`` reads only the first letter, so
    estimates group correctly in ``star_type_breakdown``.

    Args:
        bp_rp: Gaia BP-RP colour, or ``None`` when unavailable.
        gmag: Gaia broad-band G magnitude.
        dist_ly: Distance in light-years.

    Returns:
        A string like ``"M (est)"``, or ``""`` when no estimate
        is possible.
    """
    if bp_rp is None or gmag == 99.0 or dist_ly <= 0:
        return ""
    dist_pc = dist_ly / 3.26156
    abs_g = gmag - 5 * math.log10(dist_pc / 10)
    # Blue but intrinsically faint: white dwarf territory.
    if bp_rp < 1.0 and abs_g > 10.0:
        return "D (est)"
    if bp_rp < 0.0:
        return "B (est)"
    if bp_rp < 0.37:
        return "A (est)"
    if bp_rp < 0.77:
        return "F (est)"
    if bp_rp < 0.98:
        return "G (est)"
    if bp_rp < 1.84:
        return "K (est)"
    if bp_rp < 5.0:
        return "M (est)"
    return ""


def fetch_gaia_nearby(max_dist_ly: float) -> list[dict]:
    """Query Gaia DR3 via Vizier for nearby stars.

    Positions are the catalogue's ICRS values at epoch J2016.0
    propagated to J2000.0 with the Gaia proper motions. G
    magnitudes are converted to approximate V using BP-RP where
    possible and labelled with their band otherwise. There is no
    fallback catalogue: the fetch-count guard in ``main`` fails
    the run if this query returns nothing.

    Args:
        max_dist_ly: Maximum distance in light-years.

    Returns:
        A list of star dicts.  Spectral types are estimates from
        colour since Gaia does not provide MK classification.
    """
    from astroquery.vizier import Vizier

    max_dist_pc = max_dist_ly / 3.26156
    min_parallax = 1000.0 / max_dist_pc

    print(f"[3/4] Querying Gaia DR3 (parallax > {min_parallax:.1f} mas)...")
    v = Vizier(
        columns=["Source", "RA_ICRS", "DE_ICRS", "pmRA", "pmDE", "Plx", "e_Plx", "Gmag", "BP-RP"],
        row_limit=-1,
    )

    try:
        result = v.query_constraints(
            catalog="I/355/gaiadr3",
            Plx=f">{min_parallax:.1f}",
        )
    except Exception as e:
        print(f"  WARNING: Gaia query failed: {e}")
        return []

    if not result or len(result) == 0:
        print("  WARNING: No Gaia results")
        return []

    table = result[0]
    ra_j2000, dec_j2000 = propagate_to_j2000(
        _float_column(table, "RA_ICRS"), _float_column(table, "DE_ICRS"),
        _float_column(table, "pmRA"), _float_column(table, "pmDE"),
        _float_column(table, "Plx"), GAIA_DR3_EPOCH_JD,
    )
    bp_rp_col = _float_column(table, "BP-RP")

    stars = []
    for i, row in enumerate(table):
        try:
            plx = float(row["Plx"])
        except (ValueError, TypeError):
            continue
        if plx <= 0:
            continue
        try:
            e_plx = float(row["e_Plx"])
        except (ValueError, TypeError):
            continue  # skip stars with unparseable parallax errors
        if e_plx > 0 and plx / e_plx < MIN_PARALLAX_SNR:
            continue
        dist_ly = (1000.0 / plx) * 3.26156
        gmag = float(row["Gmag"]) if not np.ma.is_masked(row["Gmag"]) else 99.0
        bp_rp = float(bp_rp_col[i]) if np.isfinite(bp_rp_col[i]) else None
        sp = estimate_spectral_class(bp_rp, gmag, dist_ly)
        source_id = str(row["Source"])

        ra, dec = ra_j2000[i], dec_j2000[i]
        has_pos = bool(np.isfinite(ra) and np.isfinite(dec))

        v_est = gaia_g_to_v(gmag, bp_rp) if gmag != 99.0 else None
        if v_est is not None:
            mag, band = round(v_est, 2), "V"
        else:
            mag, band = round(gmag, 2), "G"

        stars.append({
            "name": f"Gaia DR3 {source_id}",
            "distance_ly": round(dist_ly, 4),
            "spectral_type": sp,
            "apparent_magnitude": mag,
            "magnitude_band": band,
            "known_exoplanets": 0,
            "ra_deg": round(float(ra), 4) if has_pos else None,
            "dec_deg": round(float(dec), 4) if has_pos else None,
            "_source": "gaia",
            "_pos_source": "gaia",
            "_catalogue_id": source_id,
        })

    print(f"  Found {len(stars)} stars")
    return stars


# ---------------------------------------------------------------------------
# Exoplanet data
# ---------------------------------------------------------------------------
def fetch_exoplanet_counts() -> dict[str, int]:
    """Get confirmed planet counts per host star from NASA Exoplanet Archive.

    Returns:
        A dict mapping star name variants (hostname, HIP, HD)
        to the maximum confirmed planet count.
    """
    import numpy as np  # noqa: I001
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

    print("[4/4] Querying NASA Exoplanet Archive...")
    try:
        table = NasaExoplanetArchive.query_criteria(
            table="pscomppars",
            select="hostname,hip_name,hd_name,sy_pnum",
        )
    except Exception as e:
        print(f"  WARNING: Exoplanet Archive query failed: {e}")
        return {}

    counts: dict[str, int] = {}

    def _add(key: str, pnum: int) -> None:
        """Record *pnum* for *key*, keeping the maximum."""
        if key:
            counts[key] = max(counts.get(key, 0), pnum)

    for row in table:
        pnum = int(row["sy_pnum"]) if row["sy_pnum"] else 0
        if pnum <= 0:
            continue

        hostname = str(row["hostname"]).strip()
        hip = str(row["hip_name"]).strip() if not np.ma.is_masked(row["hip_name"]) else ""
        hd = str(row["hd_name"]).strip() if not np.ma.is_masked(row["hd_name"]) else ""

        _add(hostname, pnum)
        if hip:
            _add(hip, pnum)
            hip_num = hip.replace("HIP", "").strip().split()[0]
            _add(f"HIP {hip_num}", pnum)
        if hd:
            _add(hd, pnum)

    print(f"  Found exoplanet data for {len(counts)} keys")
    return counts


# Map from common names used in our catalogue to NASA Exoplanet Archive hostnames
_EXOPLANET_NAME_ALIASES: dict[str, list[str]] = {
    "Proxima Centauri": ["Proxima Cen", "GJ 551", "Gl 551"],
    "Alpha Centauri B": ["alf Cen B", "GJ 559 B"],
    "Barnard's Star": ["Barnard's star", "GJ 699", "Gl 699"],
    "Lalande 21185": ["GJ 411", "Gl 411"],
    "Epsilon Eridani": ["eps Eri", "GJ 144", "Gl 144"],
    "Tau Ceti": ["tau Cet", "GJ 71", "Gl 71"],
    "Lacaille 9352": ["GJ 887", "Gl 887"],
    "Epsilon Indi A": ["eps Ind A", "GJ 845", "Gl 845"],
    "Luyten's Star": ["GJ 273", "Gl 273"],
    "YZ Ceti": ["YZ Cet", "GJ 54.1"],
    "Kapteyn's Star": ["Kapteyn's star", "GJ 191"],
    "Wolf 1061": ["GJ 628"],
    "Ross 128": ["GJ 447"],
    "Teegarden's Star": ["Teegarden's Star"],
    "Wolf 359": ["CN Leo", "GJ 406"],
    "Ross 154": ["GJ 729"],
    "Ross 248": ["GJ 905"],
    "Sirius A": ["Sirius", "GJ 244 A"],
    "GJ 876": ["GJ 876", "Gl 876"],
    "GJ 832": ["GJ 832", "Gl 832"],
    "GJ 1061": ["GJ 1061"],
    "GJ 667 C": ["GJ 667 C"],
    "GJ 581": ["GJ 581", "Gl 581"],
    "Pollux": ["Pollux"],
    "70 Ophiuchi A": ["70 Oph", "GJ 702"],
}


def match_exoplanets(stars: list[dict], exo_counts: dict[str, int]) -> int:
    """Apply exoplanet counts to stars using multiple matching strategies.

    Tries common-name aliases and HIP IDs to match stars against
    the NASA Exoplanet Archive data.

    Args:
        stars: Star catalogue to update (mutated in place).
        exo_counts: Mapping from star name variants to planet
            counts, as returned by ``fetch_exoplanet_counts``.

    Returns:
        Number of stars that were successfully matched.
    """
    matched = 0
    for s in stars:
        keys_to_try = [s["name"]]

        if s["name"] in _EXOPLANET_NAME_ALIASES:
            keys_to_try.extend(_EXOPLANET_NAME_ALIASES[s["name"]])

        if "_hip_id" in s:
            keys_to_try.append(f"HIP {s['_hip_id']}")
            keys_to_try.append(f"HIP{s['_hip_id']}")

        for key in keys_to_try:
            if key in exo_counts:
                s["known_exoplanets"] = exo_counts[key]
                matched += 1
                break
    return matched


# ---------------------------------------------------------------------------
# Merge and deduplicate
# ---------------------------------------------------------------------------
def _angular_sep_deg(
    ra1: float | None,
    dec1: float | None,
    ra2: float | None,
    dec2: float | None,
) -> float:
    """Compute angular separation in degrees between two sky positions.

    Uses the Vincenty formula for numerical stability at small
    angles.

    Args:
        ra1: Right ascension of the first position (degrees).
        dec1: Declination of the first position (degrees).
        ra2: Right ascension of the second position (degrees).
        dec2: Declination of the second position (degrees).

    Returns:
        Angular separation in degrees, or ``999.0`` if any
        coordinate is ``None``.
    """
    if None in (ra1, dec1, ra2, dec2):
        return 999.0  # unknown position — never match
    ra1, dec1, ra2, dec2 = (
        math.radians(ra1), math.radians(dec1),
        math.radians(ra2), math.radians(dec2),
    )
    d_ra = ra2 - ra1
    num = math.sqrt(
        (math.cos(dec2) * math.sin(d_ra)) ** 2
        + (math.cos(dec1) * math.sin(dec2)
           - math.sin(dec1) * math.cos(dec2) * math.cos(d_ra)) ** 2
    )
    den = (
        math.sin(dec1) * math.sin(dec2)
        + math.cos(dec1) * math.cos(dec2) * math.cos(d_ra)
    )
    return math.degrees(math.atan2(num, den))


def _is_catalogue_id(name: str) -> bool:
    """Return ``True`` if *name* looks like a catalogue identifier.

    Args:
        name: Star name to inspect.

    Returns:
        ``True`` for prefixes like ``HIP``, ``Gaia``, ``Gl``, etc.
    """
    return (
        name.startswith("HIP ")
        or name.startswith("Gaia ")
        or name.startswith("Gl ")
        or name.startswith("GJ ")
        or name.startswith("NN ")
        or name.startswith("Wo ")
    )


def _has_precise_position(s: dict) -> bool:
    """Whether an entry's position is modern astrometry at J2000.

    Args:
        s: Star dict, before or after merging.

    Returns:
        ``True`` for positions from HIPPARCOS or Gaia; ``False``
        for Gliese positions and hand-curated entries.
    """
    return s.get("_pos_source") in ("hipparcos", "gaia")


def _same_star(a: dict, b: dict) -> bool:
    """Heuristic: are two catalogue entries the same physical star?

    Rules, in order:

    - Two entries with HIP IDs match only when the IDs are equal.
    - Entries whose source sets overlap never match: genuine
      close pairs (binaries) appear as separate rows within one
      catalogue, and each row is a distinct object.
    - Two entries with the same common name match when close on
      the sky; two DIFFERENT common names never match.
    - Otherwise (at least one catalogue ID): positions within
      ``COINCIDENT_SEP_ARCSEC`` match unconditionally (tier 1;
      ``GLIESE_COINCIDENT_SEP_ARCSEC`` when either position is a
      coarse Gliese or curated one), and positions within
      ``MERGE_MAX_SEP_DEG`` match when the distances also agree
      within the scaled tolerance (tier 2). Tier 2 is skipped
      when both positions come from HIPPARCOS or Gaia.

    Args:
        a: First star dict.
        b: Second star dict.

    Returns:
        ``True`` if the entries likely represent the same star.
    """
    hip_a = a.get("_hip_id")
    hip_b = b.get("_hip_id")
    if hip_a and hip_b:
        return hip_a == hip_b

    if _sources(a) & _sources(b):
        return False

    sep = _angular_sep_deg(
        a.get("ra_deg"), a.get("dec_deg"),
        b.get("ra_deg"), b.get("dec_deg"),
    )

    a_common = not _is_catalogue_id(a["name"])
    b_common = not _is_catalogue_id(b["name"])
    if a_common and b_common:
        if a["name"].lower() == b["name"].lower():
            return sep < 5.0
        return False

    both_precise = _has_precise_position(a) and _has_precise_position(b)
    coincident = (
        COINCIDENT_SEP_ARCSEC if both_precise
        else GLIESE_COINCIDENT_SEP_ARCSEC
    )
    if sep < coincident / 3600.0:
        return True

    if both_precise:
        return False

    dist_diff = abs(a["distance_ly"] - b["distance_ly"])
    tol = _distance_tolerance_ly(
        min(a["distance_ly"], b["distance_ly"]),
    )
    return dist_diff < tol and sep < MERGE_MAX_SEP_DEG


def _absorb(existing: dict, star: dict) -> None:
    """Fold a duplicate entry into its canonical merged entry.

    Keeps the richer name, non-empty spectral type, V-band
    magnitude, higher exoplanet count and HIP ID, and adopts the
    distance and the position from the most reliable contributing
    catalogue (Gaia over HIPPARCOS over Gliese): the best parallax
    comes with the best astrometry, and a merged entry must not
    keep a Gliese position quantised to a second of time.

    Args:
        existing: The merged entry to keep (mutated in place).
        star: The duplicate entry being absorbed.
    """
    if (_is_catalogue_id(existing["name"])
            and not _is_catalogue_id(star["name"])):
        existing["name"] = star["name"]
    if (existing["spectral_type"] == ""
            and star["spectral_type"] != ""):
        existing["spectral_type"] = star["spectral_type"]
    if star["known_exoplanets"] > existing["known_exoplanets"]:
        existing["known_exoplanets"] = star["known_exoplanets"]
    if not existing.get("_hip_id") and star.get("_hip_id"):
        existing["_hip_id"] = star["_hip_id"]
    if (existing.get("ra_deg") is None
            and star.get("ra_deg") is not None):
        existing["ra_deg"] = star["ra_deg"]
        existing["dec_deg"] = star["dec_deg"]
        existing["_pos_source"] = star.get("_pos_source")
    if (existing.get("magnitude_band") == "G"
            and star.get("magnitude_band") == "V"):
        existing["apparent_magnitude"] = star["apparent_magnitude"]
        existing["magnitude_band"] = "V"

    q_existing = _SOURCE_QUALITY.get(
        existing.get("_dist_source") or existing.get("_source"),
        0,
    )
    q_star = _SOURCE_QUALITY.get(
        star.get("_dist_source") or star.get("_source"), 0,
    )
    if q_star > q_existing:
        existing["distance_ly"] = star["distance_ly"]
        existing["_dist_source"] = (
            star.get("_dist_source") or star.get("_source")
        )
        if star.get("ra_deg") is not None:
            existing["ra_deg"] = star["ra_deg"]
            existing["dec_deg"] = star["dec_deg"]
            existing["_pos_source"] = star.get("_pos_source")

    existing["_merged_sources"] = _sources(existing) | _sources(star)


def merge_catalogues(*catalogues: list[dict]) -> list[dict]:
    """Merge multiple star lists, deduplicating across catalogues.

    Each incoming star is absorbed into the closest (smallest
    angular separation) matching entry rather than the first one
    encountered, so binary components pair up with the right
    counterpart when both are present.

    Args:
        *catalogues: One or more star-dict lists to merge.
            Order matters: earlier catalogues are preferred for
            naming and magnitudes.

    Returns:
        A single deduplicated list of star dicts.
    """
    merged: list[dict] = []
    for catalogue in catalogues:
        for star in catalogue:
            best: dict | None = None
            best_sep = 0.0
            dec_s = star.get("dec_deg")
            for existing in merged:
                # Cheap declination pre-filter before the full
                # trigonometry: sep >= |delta dec| always.
                dec_e = existing.get("dec_deg")
                if (
                    dec_e is not None
                    and dec_s is not None
                    and abs(dec_e - dec_s) > MERGE_MAX_SEP_DEG
                ):
                    continue
                if not _same_star(existing, star):
                    continue
                sep = _angular_sep_deg(
                    existing.get("ra_deg"),
                    existing.get("dec_deg"),
                    star.get("ra_deg"), star.get("dec_deg"),
                )
                if best is None or sep < best_sep:
                    best, best_sep = existing, sep

            if best is None:
                merged.append(dict(star))
            else:
                _absorb(best, star)

    return merged


# ---------------------------------------------------------------------------
# Post-merge overrides and validation
# ---------------------------------------------------------------------------
def dedup_by_coordinates(
    stars: list[dict],
    authoritative: list[dict],
) -> int:
    """Remove catalogue-ID entries that duplicate authoritative stars.

    After EXTRA_STARS are injected, Gaia/Gliese entries for the
    same physical star may remain under catalogue designations.
    This removes them with the same rules as ``_same_star``; the
    curated entries carry no position provenance, so the wide
    distance-checked window still applies to them and a curated
    coordinate a few arcseconds off still catches its duplicate.
    """
    to_remove: list[int] = []
    auth_names = {s["name"] for s in authoritative}
    for i, s in enumerate(stars):
        if s["name"] in auth_names:
            continue  # don't remove the authoritative entry
        if not _is_catalogue_id(s["name"]):
            continue  # only remove catalogue-ID entries
        for auth in authoritative:
            if (auth.get("ra_deg") is None
                    or s.get("ra_deg") is None):
                continue
            if _same_star(s, auth):
                to_remove.append(i)
                break
    for i in sorted(set(to_remove), reverse=True):
        del stars[i]
    return len(to_remove)


def dedup_by_name(stars: list[dict]) -> int:
    """Remove duplicate names, keeping the entry with richer data.

    Args:
        stars: Star catalogue to deduplicate (mutated in place).

    Returns:
        Number of duplicate entries removed.
    """
    seen: dict[str, int] = {}
    to_remove: list[int] = []
    for i, s in enumerate(stars):
        if s["name"] in seen:
            prev_i = seen[s["name"]]
            prev = stars[prev_i]
            # Keep whichever has a HIP ID, or better spectral type
            if s.get("_hip_id") and not prev.get("_hip_id"):
                to_remove.append(prev_i)
                seen[s["name"]] = i
            else:
                to_remove.append(i)
        else:
            seen[s["name"]] = i
    for i in sorted(to_remove, reverse=True):
        del stars[i]
    return len(to_remove)


def fix_spectral_types(stars: list[dict]) -> int:
    """Normalise spectral type strings.

    Fixes observed issues from catalogue data:
    - Collapse internal multi-spaces to single space
    - Remove archaic 'd' prefix (dM → M, dK → K, dG → G)
    - Remove trailing 'J' binary indicator
    - Clear placeholder types like 'R...'
    - Uppercase range types (k-m → K-M)
    """
    fixed = 0
    for s in stars:
        sp = s.get("spectral_type", "")
        if not sp:
            continue
        original = sp

        # Collapse internal multi-spaces to single space
        while "  " in sp:
            sp = sp.replace("  ", " ")

        # Remove archaic dwarf prefix (dM5.5e → M5.5e)
        if len(sp) >= 2 and sp[0] == "d" and sp[1] in "MKGFAB":
            sp = sp[1:]

        # Remove trailing J (historical binary indicator)
        sp = sp.rstrip()
        if sp.endswith("J"):
            sp = sp[:-1].rstrip()

        # Clear placeholder types
        if sp in ("R...", "..."):
            sp = ""

        # Uppercase range types (k-m → K-M, f-g → F-G)
        if (len(sp) == 3 and sp[1] == "-"
                and sp[0].isalpha() and sp[2].isalpha()):
            sp = sp.upper()

        # Bare lowercase type with optional suffix (m+ → M+)
        if sp and sp[0].islower() and sp[0] not in "sd":
            sp = sp[0].upper() + sp[1:]

        if sp != original:
            s["spectral_type"] = sp
            fixed += 1
    return fixed


def remove_unknown_magnitudes(stars: list[dict]) -> int:
    """Remove stars with magnitude 99.0 (no photometry data).

    Args:
        stars: Star catalogue to filter (mutated in place).

    Returns:
        Number of entries removed.
    """
    before = len(stars)
    stars[:] = [s for s in stars if s["apparent_magnitude"] != 99.0]
    return before - len(stars)


def apply_overrides(stars: list[dict]) -> int:
    """Apply ``KNOWN_STAR_OVERRIDES`` to correct data for key stars.

    Args:
        stars: Star catalogue to patch (mutated in place).

    Returns:
        Number of stars that matched an override.
    """
    fixed = 0
    for s in stars:
        if s["name"] in KNOWN_STAR_OVERRIDES:
            override = KNOWN_STAR_OVERRIDES[s["name"]]
            # Remember where the catalogues put this entry so the
            # validator can tell whether the override landed on
            # the star it names.
            s["_catalogue_ra"] = s.get("ra_deg")
            s["_catalogue_dec"] = s.get("dec_deg")
            for key, val in override.items():
                s[key] = val
            # Override magnitudes are SIMBAD V magnitudes.
            s["magnitude_band"] = "V"
            fixed += 1
    return fixed


def find_positional_duplicates(
    stars: list[dict],
    max_sep_arcsec: float = DUPLICATE_SEP_ARCSEC,
) -> list[tuple[int, int, float]]:
    """Find entry pairs that look like one star listed twice.

    A pair is suspicious when the sky positions nearly coincide
    but the distances disagree by more than a few percent: the
    signature of one physical star entering from catalogues
    whose parallaxes disagree.  Not flagged: components of
    genuine multiple systems (same position AND distance),
    resolved pairs within a single source catalogue, and
    hand-curated system components (both carry common names).

    Args:
        stars: Star catalogue to scan.
        max_sep_arcsec: Angular separation threshold.

    Returns:
        A list of ``(index_a, index_b, separation_deg)`` tuples.
    """
    max_sep_deg = max_sep_arcsec / 3600.0
    order = sorted(
        (i for i, s in enumerate(stars)
         if s.get("ra_deg") is not None),
        key=lambda i: stars[i]["dec_deg"],
    )
    pairs: list[tuple[int, int, float]] = []
    for pos, i in enumerate(order):
        for j in order[pos + 1:]:
            # Sorted by declination: once the dec gap exceeds
            # the threshold nothing further can be close.
            if (stars[j]["dec_deg"] - stars[i]["dec_deg"]
                    > max_sep_deg):
                break
            a, b = stars[i], stars[j]
            if (not _is_catalogue_id(a["name"])
                    and not _is_catalogue_id(b["name"])):
                continue  # hand-curated system components
            if _sources(a) & _sources(b):
                continue  # resolved pair within one catalogue
            sep = _angular_sep_deg(
                a["ra_deg"], a["dec_deg"],
                b["ra_deg"], b["dec_deg"],
            )
            if sep >= max_sep_deg:
                continue
            d_a = a["distance_ly"]
            d_b = b["distance_ly"]
            tol = max(
                DUPLICATE_DIST_TOL_FLOOR_LY,
                DUPLICATE_DIST_TOL_FRACTION * min(d_a, d_b),
            )
            if abs(d_a - d_b) > tol:
                pairs.append((i, j, sep))
    return pairs


def validate_catalogue(stars: list[dict]) -> list[str]:
    """Run post-generation integrity checks.

    These checks catch regressions — every issue here SHOULD
    have been auto-fixed by the pipeline steps above.

    Args:
        stars: The final star catalogue to validate.

    Returns:
        A list of error messages.  An empty list means the
        catalogue is clean and ready to commit.
    """
    errors = []

    # Positional duplicates: same sky position, disagreeing
    # distance. This is exactly the corruption that duplicated
    # ~4,000 stars in the v1.0 catalogue, so its presence must
    # fail the run rather than pass silently.
    for i, j, sep in find_positional_duplicates(stars):
        errors.append(
            f"POSITIONAL_DUP: '{stars[i]['name']}' "
            f"({stars[i]['distance_ly']} ly) and "
            f"'{stars[j]['name']}' "
            f"({stars[j]['distance_ly']} ly) are "
            f"{sep * 3600:.1f} arcsec apart"
        )

    # Duplicate names (should have been caught by dedup_by_name)
    seen_names: dict[str, int] = {}
    for i, s in enumerate(stars):
        if s["name"] in seen_names:
            errors.append(
                f"DUPLICATE: '{s['name']}' at indices "
                f"{seen_names[s['name']]} and {i}"
            )
        seen_names[s["name"]] = i

    # All key stars present (should exist via EXTRA_STARS + overrides)
    for name in KNOWN_STAR_OVERRIDES:
        if name not in seen_names:
            errors.append(f"MISSING: '{name}' not in catalogue")

    # Overrides must land on the star they name. The position the
    # catalogues gave the entry (kept by apply_overrides) has to
    # agree with the override's SIMBAD position; a large gap means
    # a HIP or Gliese name mapping points at a different star,
    # which the override would then silently overwrite.
    for s in stars:
        if s["name"] not in KNOWN_STAR_OVERRIDES:
            continue
        cat_ra = s.get("_catalogue_ra")
        cat_dec = s.get("_catalogue_dec")
        if cat_ra is None or cat_dec is None:
            continue
        ov = KNOWN_STAR_OVERRIDES[s["name"]]
        sep_arcsec = _angular_sep_deg(
            cat_ra, cat_dec, ov["ra_deg"], ov["dec_deg"],
        ) * 3600.0
        if sep_arcsec > OVERRIDE_MAX_SEP_ARCSEC:
            errors.append(
                f"OVERRIDE_MISMATCH: '{s['name']}' override "
                f"landed on a catalogue entry {sep_arcsec:.0f} "
                f"arcsec away (limit "
                f"{OVERRIDE_MAX_SEP_ARCSEC:.0f}); a name "
                f"mapping points at the wrong star"
            )

    # Value range checks
    for i, s in enumerate(stars):
        d = s["distance_ly"]
        if not (0 < d <= MAX_RADIUS_LY):
            errors.append(
                f"RANGE: '{s['name']}' distance {d} "
                f"outside (0, {MAX_RADIUS_LY}]"
            )
        mag = s["apparent_magnitude"]
        if not (-2 < mag < 30):
            errors.append(
                f"RANGE: '{s['name']}' magnitude {mag} "
                f"outside (-2, 30)"
            )
        ra = s.get("ra_deg")
        if ra is not None and not (0 <= ra < 360):
            errors.append(
                f"RANGE: '{s['name']}' RA {ra} "
                f"outside [0, 360)"
            )
        dec = s.get("dec_deg")
        if dec is not None and not (-90 <= dec <= 90):
            errors.append(
                f"RANGE: '{s['name']}' Dec {dec} "
                f"outside [-90, 90]"
            )

    return errors


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------
def write_stars(
    stars: list[dict],
    output_path: Path | None = None,
) -> bool:
    """Sort by distance and write the star catalogue to ``data/stars.json``.

    The file is written to a temporary sibling and moved into
    place with ``os.replace`` so an interrupted run can never
    leave a truncated catalogue behind.  When the serialised
    content is identical to what is already on disk, nothing is
    written, so automated runs can tell "refreshed" from
    "actually changed".

    Args:
        stars: Final validated star catalogue.
        output_path: Override the destination (used by tests).

    Returns:
        ``True`` when the file on disk changed.
    """
    stars.sort(key=lambda s: (s["distance_ly"], s["name"]))

    clean = []
    for s in stars:
        clean.append({
            "name": s["name"],
            "distance_ly": s["distance_ly"],
            "spectral_type": s["spectral_type"],
            "apparent_magnitude": s["apparent_magnitude"],
            "magnitude_band": s.get("magnitude_band"),
            "known_exoplanets": s["known_exoplanets"],
            "ra_deg": s.get("ra_deg"),
            "dec_deg": s.get("dec_deg"),
            # Provenance of the distance measurement.
            "source": (
                s.get("_dist_source")
                or s.get("_source")
                or s.get("source")
                or "curated"
            ),
            # Every catalogue this entry drew from, so the
            # positional-duplicate check can distinguish real
            # component pairs (shared source) from duplicates
            # on the written data exactly as the validator
            # does on the in-memory entries.
            "sources": sorted(_sources(s)) or ["curated"],
        })

    if output_path is None:
        output_path = (
            Path(__file__).resolve().parent.parent.parent
            / "data" / "stars.json"
        )
    payload = json.dumps(clean, indent=4)

    if output_path.exists():
        try:
            unchanged = (
                output_path.read_text(encoding="utf-8")
                == payload
            )
        except OSError:
            unchanged = False
        if unchanged:
            print(
                f"\n{output_path.name} unchanged "
                f"({len(clean)} stars); not rewritten"
            )
            return False

    tmp_path = output_path.with_name(output_path.name + ".tmp")
    # newline="\n" keeps output byte-identical across platforms
    # (Windows text mode would otherwise write CRLF).
    tmp_path.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp_path, output_path)

    print(f"\nWrote {len(clean)} stars to {output_path}")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Fetch, merge, clean, validate, and write the star catalogue."""
    print("=" * 60)
    print("Your First Light — Star Catalogue Updater")
    print("=" * 60)
    print()

    # Fetch from multiple catalogues
    hip_stars = fetch_hipparcos(MAX_RADIUS_LY)
    gliese_stars = fetch_gliese(MAX_RADIUS_LY)
    gaia_stars = fetch_gaia_nearby(MAX_RADIUS_LY)

    # Refuse to continue if any source came back empty or thin
    # (a catalogue built from the remainder would look plausible
    # while silently missing thousands of stars) ...
    fetch_errors = check_fetch_counts({
        "hipparcos": len(hip_stars),
        "gliese": len(gliese_stars),
        "gaia": len(gaia_stars),
    })
    # ... or with positions at the wrong epoch: fast-moving reference
    # stars must come back where they belong at J2000.0.
    fetch_errors += check_reference_positions(hip_stars, "hipparcos")
    fetch_errors += check_reference_positions(gliese_stars, "gliese")
    fetch_errors += check_reference_positions(gaia_stars, "gaia")
    if fetch_errors:
        print(f"\nERROR: {len(fetch_errors)} fetch failure(s):")
        for e in fetch_errors:
            print(f"  - {e}")
        print("\nData NOT written. Upstream sources are "
              "unavailable or degraded; retry later.")
        sys.exit(1)

    # Merge all catalogue results (order matters: prefer named sources first)
    print("\nMerging catalogues...")
    all_stars = merge_catalogues(hip_stars, gliese_stars, gaia_stars)
    print(f"  Merged to {len(all_stars)} unique stars")

    # Add/override with hand-verified EXTRA_STARS data.
    # If a name already exists, REPLACE the catalogue entry (EXTRA_STARS wins).
    extras_added = 0
    extras_replaced = 0
    existing_by_name = {s["name"]: i for i, s in enumerate(all_stars)}
    for extra in EXTRA_STARS:
        if extra["name"] in existing_by_name:
            idx = existing_by_name[extra["name"]]
            all_stars[idx] = dict(extra)
            extras_replaced += 1
        else:
            all_stars.append(dict(extra))
            extras_added += 1
    print(f"  Added {extras_added}, replaced {extras_replaced} "
          f"from EXTRA_STARS")

    # Remove catalogue entries that duplicate EXTRA_STARS by position.
    # EXTRA_STARS are hand-verified; Gaia/Gliese catalogue IDs for the
    # same physical star should be removed.
    extra_deduped = dedup_by_coordinates(all_stars, EXTRA_STARS)
    print(f"  Removed {extra_deduped} catalogue duplicates of "
          f"EXTRA_STARS entries")

    # Auto-fix pipeline: dedup, spectral types, missing magnitudes
    deduped = dedup_by_name(all_stars)
    sp_fixed = fix_spectral_types(all_stars)
    mag_removed = remove_unknown_magnitudes(all_stars)
    print(f"  Auto-fix: {deduped} duplicates removed, "
          f"{sp_fixed} spectral types fixed, "
          f"{mag_removed} no-magnitude entries dropped")

    # Fetch and apply exoplanet counts (before overrides so overrides win).
    # A failed or thin archive response must fail the run: carrying on
    # would zero out known_exoplanets across the catalogue while every
    # other check stays green.
    exo_counts = fetch_exoplanet_counts()
    fetch_errors = check_fetch_counts({
        "exoplanet_archive": len(exo_counts),
    })
    if fetch_errors:
        print(f"\nERROR: {len(fetch_errors)} fetch failure(s):")
        for e in fetch_errors:
            print(f"  - {e}")
        print("\nData NOT written. Upstream sources are "
              "unavailable or degraded; retry later.")
        sys.exit(1)
    matched = match_exoplanets(all_stars, exo_counts)
    print(f"  Matched exoplanets to {matched} stars")

    # Apply known-star overrides as final correction
    fixed = apply_overrides(all_stars)
    print(f"  Applied overrides to {fixed} stars")

    # Validate before writing — any errors indicate a pipeline issue
    errors = validate_catalogue(all_stars)
    if errors:
        print(f"\nERROR: {len(errors)} validation failure(s):")
        for e in errors:
            print(f"  - {e}")
        print("\nData NOT written. Fix the issues above "
              "before retrying.")
        sys.exit(1)

    print("\nValidation passed")
    changed = write_stars(all_stars)

    # Summary
    within_15 = sum(1 for s in all_stars if s["distance_ly"] <= 15)
    within_25 = sum(1 for s in all_stars if s["distance_ly"] <= 25)
    within_50 = sum(1 for s in all_stars if s["distance_ly"] <= 50)
    total_planets = sum(s["known_exoplanets"] for s in all_stars)
    print("\nSummary:")
    print(f"  Stars within 15 ly: {within_15}")
    print(f"  Stars within 25 ly: {within_25}")
    print(f"  Stars within 50 ly: {within_50}")
    print(f"  Total stars: {len(all_stars)}")
    print(f"  Total known exoplanets: {total_planets}")

    print()
    if changed:
        print("Done! Review the diff, then commit data/stars.json")
        print("(the scheduled workflow does this via a pull request).")
    else:
        print("Done! Catalogue already up to date.")


if __name__ == "__main__":
    main()
