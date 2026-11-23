"""Querying VizieR, and reading the rows of any catalogue table.

Each fetcher asks for its catalogue's native position, proper motion
and parallax columns and derives J2000.0 positions itself (see
``astrometry``).
"""

from functools import partial
from io import BytesIO
from typing import Any

import numpy as np
from astropy.io import votable

from tools.updaters.retry import with_retries
from tools.updaters.stars.astrometry import parallax_to_ly
from tools.updaters.stars.photometry import MISSING_MAGNITUDE

# The CDS primary first, then the mirror at the Center for Astrophysics,
# which holds Gliese in full, so a CDS outage need not fail the
# refresh.
VIZIER_HOSTS = ("vizier.cds.unistra.fr", "vizier.cfa.harvard.edu")
# astroquery's row_limit for "every matching row".
NO_ROW_LIMIT = -1
# A parallax measured to less than this many standard errors gives no
# usable distance.
MIN_PARALLAX_SNR = 5


def query_catalogue(
    label: str,
    catalogue: str,
    columns: list[str],
    **constraints: str,
) -> Any | None:
    """Fetches the rows of a VizieR catalogue that meet the constraints.

    Asks each of ``VIZIER_HOSTS`` in turn until one answers with rows.
    A failed request, or an answer with no rows and an error from the
    server (VizieR reports a lost database connection that way), is
    retried. When a host answers with no rows and no error, the
    warnings it gives are printed, since they say why.

    Args:
        label: The source's name in warnings, such as ``"Gliese"``.
        catalogue: The VizieR identifier, such as ``"V/70A/catalog"``.
        columns: The VizieR column names to return.
        **constraints: Column constraints, such as ``plx=">20.38475"``.

    Returns:
        The astropy table of matching rows, or ``None`` after printing
        a warning when every host failed or matched nothing. The fetch
        guards then fail the run, so no error is raised here.
    """
    # astroquery is only in the catalogue dependency group; importing it
    # here lets the rest of the updater, and its tests, run without it.
    from astroquery.vizier import Vizier

    for host in VIZIER_HOSTS:
        vizier = Vizier(
            columns=columns, row_limit=NO_ROW_LIMIT, vizier_server=host
        )
        try:
            answer = with_retries(
                partial(_query, vizier, catalogue, constraints),
                f"{label} query to {host}",
            )
        except Exception as e:
            # Any failure, from DNS to an HTTP error page, means the
            # same: this host returned nothing usable.
            print(f"  WARNING: {label} query to {host} failed: {e}")
            continue
        tables = _tables_with_rows(answer)
        if tables:
            return tables[0].to_table(use_names_over_ids=True)
        print(f"  WARNING: No {label} results from {host}")
        for warning in _info_values(answer, "warning"):
            print(f"    VizieR warning: {warning}")
    return None


def _query(vizier: Any, catalogue: str, constraints: dict[str, str]) -> Any:
    """Sends one query and parses the VOTable answer as astroquery would.

    astroquery's own parser drops the INFO elements that say why an
    answer is empty, so the VOTable is parsed here.

    Raises:
        RuntimeError: The answer has no rows and reports a server error.
    """
    # A retry has to reach the server, not astroquery's cache, and a
    # refresh must not reuse an answer from an earlier run.
    response = vizier.query_constraints_async(
        catalog=catalogue, cache=False, **constraints
    )
    response.raise_for_status()
    answer = votable.parse(
        BytesIO(response.content), verify="ignore", invalid="mask"
    )
    errors = _info_values(answer, "error")
    if errors and not _tables_with_rows(answer):
        raise RuntimeError(f"VizieR error: {'; '.join(errors)}")
    return answer


def _tables_with_rows(answer: Any) -> list[Any]:
    return [t for t in answer.iter_tables() if len(t.array)]


def _info_values(answer: Any, name: str) -> list[str]:
    """The non-blank text of the INFO elements called ``name``, any case.

    VizieR spreads one message over several INFO elements, some blank or
    with no value, and pads them with runs of spaces, so the spaces are
    collapsed. The parser leaves a missing attribute as ``None``.
    """
    values = (
        " ".join((info.value or "").split())
        for info in answer.iter_info()
        if (info.name or "").lower() == name
    )
    return [v for v in values if v]


def float_column(table: Any, name: str) -> np.ndarray:
    """A table column as a float array, with masked cells as NaN."""
    return np.ma.filled(np.ma.asarray(table[name], dtype=float), np.nan)


def text_cell(value: Any) -> str:
    """A table cell as text with runs of spaces collapsed.

    A masked cell gives ``""``.
    """
    if np.ma.is_masked(value):
        return ""
    return " ".join(str(value).split())


def magnitude_cell(value: Any) -> float:
    """A magnitude cell, or ``MISSING_MAGNITUDE`` when it is masked."""
    return float(value) if not np.ma.is_masked(value) else MISSING_MAGNITUDE


def row_distance_ly(
    row: Any, plx_column: str, e_plx_column: str
) -> float | None:
    """The distance a row's parallax gives, if it is usable.

    Returns:
        The distance in light-years, or ``None`` when the parallax or
        its error is missing or does not parse, either is not
        positive, or the parallax is below ``MIN_PARALLAX_SNR``
        standard errors.
    """
    if np.ma.is_masked(row[plx_column]) or np.ma.is_masked(row[e_plx_column]):
        return None
    try:
        plx = float(row[plx_column])
    except (ValueError, TypeError):
        return None
    # A value may also be missing as NaN, which fails every comparison,
    # so each test is written to pass only a value that is there.
    if not plx > 0:
        return None
    try:
        e_plx = float(row[e_plx_column])
    except (ValueError, TypeError):
        return None
    if not e_plx > 0 or plx / e_plx < MIN_PARALLAX_SNR:
        return None
    return parallax_to_ly(plx)
