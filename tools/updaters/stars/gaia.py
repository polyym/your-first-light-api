"""Gaia DR3: most of the catalogue, with the best parallaxes.

The rows come from the ESA Gaia archive by ADQL rather than from
VizieR, whose mirrors refuse an all-sky cut on parallax alone and ask
for a target position, so only its primary host could ever serve it.
"""

from typing import Any

import numpy as np

from tools.updaters.retry import with_retries
from tools.updaters.stars.astrometry import (
    GAIA_DR3_EPOCH_JD,
    min_parallax_mas,
    propagate_to_j2000,
)
from tools.updaters.stars.entry import Star, catalogue_entry
from tools.updaters.stars.photometry import (
    MISSING_MAGNITUDE,
    estimate_spectral_class,
    gaia_g_to_v,
)
from tools.updaters.stars.vizier import (
    float_column,
    magnitude_cell,
    row_distance_ly,
)

ARCHIVE_TABLE = "gaiadr3.gaia_source"
_COLUMNS = (
    "source_id",
    "ra",
    "dec",
    "pmra",
    "pmdec",
    "parallax",
    "parallax_error",
    "phot_g_mean_mag",
    "bp_rp",
    "ruwe",
)
# Above this renormalised unit weight error the single-star astrometric
# solution does not fit the observations (Lindegren et al. 2018,
# GAIA-C3-TN-LU-LL-124). Most such rows are unresolved binaries whose
# parallaxes are sound, so only a row whose parallax is also weak is
# left out: those with a parallax under 20 standard errors move across
# the sky at a median 2.6 km/s, as distant stars with spurious
# parallaxes would, against 27 km/s for the rest.
MAX_RUWE = 1.4
MIN_PARALLAX_SNR_AT_HIGH_RUWE = 20


def archive_query(min_parallax: float) -> str:
    """The ADQL for every Gaia DR3 source with a larger parallax in mas.

    The rows are ordered by source ID, so every run reads them in the
    same order.
    """
    return (
        f"SELECT {', '.join(_COLUMNS)} FROM {ARCHIVE_TABLE} "
        f"WHERE parallax > {min_parallax} ORDER BY source_id"
    )


def archive_count_query(min_parallax: float) -> str:
    """The ADQL counting the rows that ``archive_query`` should return."""
    return (
        f"SELECT COUNT(*) FROM {ARCHIVE_TABLE} WHERE parallax > {min_parallax}"
    )


class IncompleteAnswerError(Exception):
    """The archive did not send every matching row exactly once."""


def fetch_gaia(max_dist_ly: float) -> list[Star]:
    """Fetches the Gaia DR3 stars within ``max_dist_ly`` light-years.

    Positions are the catalogue's ICRS values at epoch J2016.0,
    propagated to J2000.0 with its proper motions. Rows whose RUWE is
    above ``MAX_RUWE`` are left out when their parallax is under
    ``MIN_PARALLAX_SNR_AT_HIGH_RUWE`` standard errors, and a missing
    RUWE or parallax error counts against a row. G magnitudes
    become approximate V magnitudes where the BP-RP colour allows, and
    keep band "G" otherwise. Gaia gives no MK types, so spectral types
    are estimates from colour and absolute magnitude. Each entry also
    carries its source ID in ``_gaia_id``.

    Returns:
        The entries, or an empty list when the query failed. No other
        catalogue stands in for Gaia: the fetch guard then fails the
        run.
    """
    min_parallax = min_parallax_mas(max_dist_ly)
    print(f"[3/4] Querying Gaia DR3 (parallax > {min_parallax} mas)...")
    table = _query_archive(
        archive_query(min_parallax), archive_count_query(min_parallax)
    )
    if table is None:
        return []

    ra_j2000, dec_j2000 = propagate_to_j2000(
        float_column(table, "ra"),
        float_column(table, "dec"),
        float_column(table, "pmra"),
        float_column(table, "pmdec"),
        float_column(table, "parallax"),
        GAIA_DR3_EPOCH_JD,
    )
    bp_rp_col = float_column(table, "bp_rp")
    # Gaia gives every source with a parallax a RUWE and a parallax
    # error. One that came without would read as NaN, which fails
    # every comparison, so the test below is written to pass only
    # values that are there.
    ruwe_col = float_column(table, "ruwe")
    snr_col = float_column(table, "parallax") / float_column(
        table, "parallax_error"
    )
    stars = []
    unreliable = 0
    for i, row in enumerate(table):
        if (
            not ruwe_col[i] <= MAX_RUWE
            and not snr_col[i] >= MIN_PARALLAX_SNR_AT_HIGH_RUWE
        ):
            unreliable += 1
            continue
        distance_ly = row_distance_ly(row, "parallax", "parallax_error")
        if distance_ly is None:
            continue
        gmag = magnitude_cell(row["phot_g_mean_mag"])
        bp_rp = float(bp_rp_col[i]) if np.isfinite(bp_rp_col[i]) else None
        spectral_type = estimate_spectral_class(
            bp_rp, gmag, distance_ly, parallax_snr=float(snr_col[i])
        )
        source_id = str(row["source_id"])
        v_est = gaia_g_to_v(gmag, bp_rp) if gmag != MISSING_MAGNITUDE else None
        star = catalogue_entry(
            name=f"Gaia DR3 {source_id}",
            distance_ly=distance_ly,
            spectral_type=spectral_type,
            magnitude=gmag if v_est is None else v_est,
            band="G" if v_est is None else "V",
            ra_deg=ra_j2000[i],
            dec_deg=dec_j2000[i],
            source="gaia",
            catalogue_id=source_id,
        )
        star["_gaia_id"] = source_id
        stars.append(star)

    print(
        f"  Dropped {unreliable} rows with RUWE above {MAX_RUWE} and a "
        f"parallax under {MIN_PARALLAX_SNR_AT_HIGH_RUWE} standard errors"
    )
    print(f"  Found {len(stars)} stars")
    return stars


def _query_archive(adql: str, count_adql: str) -> Any | None:
    """Runs an ADQL query on the ESA Gaia archive, with retries.

    The archive can end an answer early without saying so, so each
    answer is checked against the archive's own count of matching rows
    and for repeated rows, and one that fails either check is retried
    like any other failure.

    Returns:
        The astropy table of results, or ``None`` after printing a
        warning when the query failed, came back short or with
        repeated rows, or matched nothing.
    """
    # astroquery is only in the catalogue dependency group; importing it
    # here lets the rest of the updater, and its tests, run without it.
    from astroquery.gaia import Gaia

    def complete_answer() -> Any:
        table = Gaia.launch_job_async(adql).get_results()
        matching = int(Gaia.launch_job_async(count_adql).get_results()[0][0])
        if len(table) != matching:
            raise IncompleteAnswerError(
                f"the archive sent {len(table)} of {matching} matching rows"
            )
        if len(set(table["source_id"])) != len(table):
            raise IncompleteAnswerError("the archive sent repeated rows")
        return table

    try:
        table = with_retries(complete_answer, "Gaia archive query")
    except Exception as e:
        # Any failure, from DNS to a failed job, means the same: the
        # archive returned nothing usable.
        print(f"  WARNING: Gaia archive query failed: {e}")
        return None
    if not len(table):
        print("  WARNING: No Gaia results")
        return None
    return table
