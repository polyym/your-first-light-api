"""The Gliese Catalogue of Nearby Stars (3rd edition, CNS3).

It adds faint nearby stars that HIPPARCOS missed, but its positions are
coarse B1950 values and many of its parallaxes are photometric.
"""

import numpy as np

from tools.updaters.stars.astrometry import (
    B1950_JD,
    MAS_PER_ARCSEC,
    gliese_b1950_to_icrs,
    min_parallax_mas,
    propagate_to_j2000,
)
from tools.updaters.stars.curated import (
    DUPLICATE_GLIESE_IDS,
    GLIESE_COMMON_NAMES,
)
from tools.updaters.stars.entry import Star, catalogue_entry
from tools.updaters.stars.vizier import (
    float_column,
    magnitude_cell,
    query_catalogue,
    row_distance_ly,
    text_cell,
)

CATALOGUE = "V/70A/catalog"
_COLUMNS = [
    "Name",
    "Comp",
    "RAB1950",
    "DEB1950",
    "pm",
    "pmPA",
    "plx",
    "e_plx",
    "Vmag",
    "Sp",
]


def gliese_name(name: str, comp: str) -> str:
    """The designation of one Gliese catalogue row.

    The catalogue lists a resolved multiple system as one row per
    component, with the component letter in its own column. ``Name``
    alone is not unique (Gl 451 A and B, Gl 4 A and B), so the
    component is part of the designation, as in ``"Gl 559 A"``.

    Args:
        name: The ``Name`` cell, such as ``"Gl 559"``.
        comp: The ``Comp`` cell, such as ``"A"`` or ``""``.

    Returns:
        The designation with single spaces.
    """
    return " ".join(f"{name} {comp}".split())


def fetch_gliese(max_dist_ly: float) -> list[Star]:
    """Fetches the Gliese stars within ``max_dist_ly`` light-years.

    Positions are the catalogue's B1950 values converted to ICRS and
    propagated from epoch B1950.0 to J2000.0 with its total proper
    motion and position angle. A component of a multiple system also
    carries the system's designation in ``_gliese_system``. The rows in
    ``DUPLICATE_GLIESE_IDS`` are left out.

    Returns:
        The entries, or an empty list when the query failed.
    """
    min_parallax = min_parallax_mas(max_dist_ly)
    print("[2/4] Querying Gliese Catalogue of Nearby Stars...")
    table = query_catalogue(
        "Gliese", CATALOGUE, _COLUMNS, plx=f">{min_parallax}"
    )
    if table is None:
        return []

    ra_b1950, dec_b1950 = gliese_b1950_to_icrs(
        [text_cell(x) for x in table["RAB1950"]],
        [text_cell(x) for x in table["DEB1950"]],
    )
    pm_arcsec = np.nan_to_num(float_column(table, "pm"))
    pa_rad = np.radians(np.nan_to_num(float_column(table, "pmPA")))
    ra_j2000, dec_j2000 = propagate_to_j2000(
        ra_b1950,
        dec_b1950,
        pm_arcsec * MAS_PER_ARCSEC * np.sin(pa_rad),
        pm_arcsec * MAS_PER_ARCSEC * np.cos(pa_rad),
        float_column(table, "plx"),
        B1950_JD,
    )
    stars = []
    for i, row in enumerate(table):
        distance_ly = row_distance_ly(row, "plx", "e_plx")
        system = text_cell(row["Name"])
        component = text_cell(row["Comp"])
        designation = gliese_name(system, component)
        if distance_ly is None or designation in DUPLICATE_GLIESE_IDS:
            continue
        star = catalogue_entry(
            name=GLIESE_COMMON_NAMES.get(designation, designation),
            distance_ly=distance_ly,
            spectral_type=text_cell(row["Sp"]),
            magnitude=magnitude_cell(row["Vmag"]),
            band="V",
            ra_deg=ra_j2000[i],
            dec_deg=dec_j2000[i],
            source="gliese",
            catalogue_id=designation,
        )
        if component:
            star["_gliese_system"] = system
        stars.append(star)

    print(f"  Found {len(stars)} stars")
    return stars
