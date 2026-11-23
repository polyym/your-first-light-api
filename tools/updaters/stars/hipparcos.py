"""HIPPARCOS: bright stars, with Gaia DR3's distance where it is sound.

The rows come from the ESA Gaia archive, which holds both HIPPARCOS
reductions and Gaia DR3's own match of each HIPPARCOS star, so the
archive joins them. Positions, proper motions and parallaxes are those of
the 2007 reduction (van Leeuwen 2007), whose parallaxes are several
times more precise for bright stars than the 1997 catalogue's. V
magnitudes and spectral types are the 1997 catalogue's, as the 2007
reduction has neither.
"""

from typing import Any

import numpy as np
from astropy.table import unique, vstack

from tools.updaters.stars.astrometry import (
    HIPPARCOS_EPOCH_JD,
    min_parallax_mas,
    parallax_to_ly,
    propagate_to_j2000,
)
from tools.updaters.stars.curated import (
    HIP_COMMON_NAMES,
    SPURIOUS_HIP_IDS,
)
from tools.updaters.stars.entry import Star, catalogue_entry
from tools.updaters.stars.gaia import (
    ARCHIVE_TABLE as GAIA_TABLE,
)
from tools.updaters.stars.gaia import (
    query_archive,
    reliable_parallax,
)
from tools.updaters.stars.photometry import MISSING_MAGNITUDE, gaia_g_to_v
from tools.updaters.stars.vizier import (
    float_column,
    magnitude_cell,
    row_distance_ly,
    text_cell,
)

NEW_REDUCTION_TABLE = "public.hipparcos_newreduction"
MAIN_CATALOGUE_TABLE = "public.hipparcos"
# Gaia DR3's match of each HIPPARCOS star, one row per star.
BEST_NEIGHBOUR_TABLE = "gaiadr3.hipparcos2_best_neighbour"
# A star whose 2007 parallax is within this many standard errors of the
# cut may still be inside it, and its Gaia DR3 row, matched in the
# merge, then decides: beta Leporis is 160.4 ly away by HIPPARCOS and
# 156.3 by Gaia. The merge drops those that stay beyond.
EDGE_PARALLAX_ERRORS = 3
# A HIPPARCOS V and the V that Gaia's G and colour give for the same
# star differ by well under this. Of the 5,258 HIPPARCOS stars within
# 160 ly that Gaia DR3 matches, 14 differ by more, all by over 3 mag:
# faint neighbours of bright stars that Gaia measures poorly.
HIPPARCOS_GAIA_MAX_MAG_DIFF = 2.0
_COLUMNS = (
    "n.hip",
    "n.ra",
    "n.dec",
    "n.pm_ra",
    "n.pm_de",
    "n.plx",
    "n.e_plx",
    "h.vmag",
    "h.sptype",
    "b.source_id",
    "g.parallax",
    "g.parallax_error",
    "g.ruwe",
    "g.phot_g_mean_mag",
    "g.bp_rp",
)


def archive_queries(min_parallax: float) -> list[tuple[str, str]]:
    """The ADQL for every star that may have a larger parallax in mas.

    Two queries, each with the query that counts the rows it should
    return: the stars whose 2007 parallax is within
    ``EDGE_PARALLAX_ERRORS`` standard errors of it or larger, and those
    whose Gaia DR3 match has a larger one. One query for both runs for
    up to about 47 s of the 60 s the archive gives an anonymous job;
    apart, each takes under half of it. Each row carries the star's
    match where Gaia has one, and the rows are ordered by HIP number,
    so every run reads them in the same order.
    """
    by_hipparcos = (
        f"FROM {NEW_REDUCTION_TABLE} AS n "
        f"LEFT OUTER JOIN {MAIN_CATALOGUE_TABLE} AS h ON h.hip = n.hip "
        f"LEFT OUTER JOIN {BEST_NEIGHBOUR_TABLE} AS b "
        f"ON b.original_ext_source_id = n.hip "
        f"LEFT OUTER JOIN {GAIA_TABLE} AS g ON g.source_id = b.source_id "
        f"WHERE n.plx + {EDGE_PARALLAX_ERRORS} * n.e_plx > {min_parallax}"
    )
    # From the Gaia side, so the archive can use its index on parallax.
    by_gaia = (
        f"FROM {GAIA_TABLE} AS g "
        f"JOIN {BEST_NEIGHBOUR_TABLE} AS b ON b.source_id = g.source_id "
        f"JOIN {NEW_REDUCTION_TABLE} AS n ON n.hip = b.original_ext_source_id "
        f"LEFT OUTER JOIN {MAIN_CATALOGUE_TABLE} AS h ON h.hip = n.hip "
        f"WHERE g.parallax > {min_parallax}"
    )
    return [
        (
            f"SELECT {', '.join(_COLUMNS)} {rows} ORDER BY n.hip",
            f"SELECT COUNT(*) {rows}",
        )
        for rows in (by_hipparcos, by_gaia)
    ]


def fetch_hipparcos(max_dist_ly: float) -> list[Star]:
    """Fetches the HIPPARCOS stars that may be within ``max_dist_ly``.

    Each star's distance is that of its Gaia DR3 match (``_gaia_match``)
    where it has one, and that of its 2007 parallax, of five standard
    errors or more, where it has not; a star with neither is left out.
    HIPPARCOS parallaxes have errors of about 1 mas at the 20 mas cut,
    so without the match some 350 stars from beyond the edge scatter
    in. An entry may lie beyond ``max_dist_ly`` until the merge, which
    drops it, with any Gliese row it absorbs, unless a Gaia row puts it
    inside. The entries in ``SPURIOUS_HIP_IDS`` are left out.

    Positions are the 2007 reduction's ICRS values at epoch J1991.25,
    propagated to J2000.0 with its proper motions. Each entry carries
    its HIP number in ``_hip_id`` and, where it has a Gaia DR3 match,
    that source's ID in ``_gaia_id``, so the merge joins it to that
    Gaia row and no other.

    Returns:
        The entries, or an empty list when either query failed.
    """
    min_parallax = min_parallax_mas(max_dist_ly)
    print(f"[1/4] Querying HIPPARCOS (parallax > {min_parallax} mas)...")
    answers = []
    for label, (adql, count_adql) in zip(
        ("HIPPARCOS (2007 parallax)", "HIPPARCOS (Gaia match)"),
        archive_queries(min_parallax),
        strict=True,
    ):
        answer = query_archive(label, adql, count_adql, "hip")
        if answer is None:
            return []
        answers.append(answer)
    # Most stars inside the cut are in both answers, as the same row.
    table = unique(vstack(answers), keys="hip")

    kept: list[int] = []
    matches: list[tuple[str, float] | None] = []
    parallaxes: list[float] = []
    for i, row in enumerate(table):
        if int(row["hip"]) in SPURIOUS_HIP_IDS:
            continue
        match = _gaia_match(row, magnitude_cell(row["vmag"]))
        if match is None and row_distance_ly(row, "plx", "e_plx") is None:
            continue
        kept.append(i)
        matches.append(match)
        parallaxes.append(float(row["plx"]) if match is None else match[1])
    rows = table[np.array(kept, dtype=int)]

    # Each star moves with the parallax that gives its distance.
    ra_j2000, dec_j2000 = propagate_to_j2000(
        float_column(rows, "ra"),
        float_column(rows, "dec"),
        float_column(rows, "pm_ra"),
        float_column(rows, "pm_de"),
        np.array(parallaxes),
        HIPPARCOS_EPOCH_JD,
    )
    stars = []
    for i, (row, match, parallax) in enumerate(
        zip(rows, matches, parallaxes, strict=True)
    ):
        hip_id = int(row["hip"])
        star = catalogue_entry(
            name=HIP_COMMON_NAMES.get(hip_id, f"HIP {hip_id}"),
            distance_ly=parallax_to_ly(parallax),
            spectral_type=text_cell(row["sptype"]),
            magnitude=magnitude_cell(row["vmag"]),
            band="V",
            ra_deg=ra_j2000[i],
            dec_deg=dec_j2000[i],
            source="hipparcos",
            catalogue_id=str(hip_id),
        )
        star["_hip_id"] = hip_id
        if match:
            star["_gaia_id"] = match[0]
        stars.append(star)

    matched = sum(1 for m in matches if m)
    print(f"  Found {len(stars)} stars, {matched} with a Gaia DR3 match")
    return stars


def _gaia_match(row: Any, v_mag: float) -> tuple[str, float] | None:
    """A row's Gaia DR3 match, where it is the star and measures it well.

    Gaia DR3 matches each HIPPARCOS star by position and proper motion.
    For some bright stars that Gaia measures poorly, the match is a
    faint neighbour, Alpha Centauri B's a source of G 21, so a match
    more than ``HIPPARCOS_GAIA_MAX_MAG_DIFF`` from the star's V is no
    match. Gaia's G is compared as V where its colour allows, and a
    missing magnitude on either side agrees. Its parallax must be at
    least five standard errors and pass the RUWE rule. Where it is not,
    the merge may join the star to a Gaia row by position instead:
    some matches are a duplicate source with no parallax, beside the
    row that holds one.

    Returns:
        The source ID and parallax in mas, or ``None``.
    """
    # A row with no match has no Gaia parallax either.
    if row_distance_ly(row, "parallax", "parallax_error") is None:
        return None
    parallax = float(row["parallax"])
    parallax_snr = parallax / float(row["parallax_error"])
    if not reliable_parallax(_float_cell(row["ruwe"]), parallax_snr):
        return None
    gmag = magnitude_cell(row["phot_g_mean_mag"])
    if MISSING_MAGNITUDE not in (gmag, v_mag):
        bp_rp = _float_cell(row["bp_rp"])
        gaia_v = gaia_g_to_v(gmag, bp_rp if np.isfinite(bp_rp) else None)
        gaia_mag = gmag if gaia_v is None else gaia_v
        if abs(gaia_mag - v_mag) > HIPPARCOS_GAIA_MAX_MAG_DIFF:
            return None
    return str(row["source_id"]), parallax


def _float_cell(value: Any) -> float:
    """A number cell, or NaN when it is masked."""
    return float("nan") if np.ma.is_masked(value) else float(value)
