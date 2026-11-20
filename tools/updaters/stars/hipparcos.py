"""The HIPPARCOS catalogue: bright stars with good parallaxes."""

from tools.updaters.stars.astrometry import (
    HIPPARCOS_EPOCH_JD,
    min_parallax_mas,
    propagate_to_j2000,
)
from tools.updaters.stars.curated import (
    HIP_COMMON_NAMES,
    SPURIOUS_HIP_IDS,
)
from tools.updaters.stars.entry import Star, catalogue_entry
from tools.updaters.stars.vizier import (
    float_column,
    magnitude_cell,
    query_catalogue,
    row_distance_ly,
    text_cell,
)

CATALOGUE = "I/239/hip_main"
_COLUMNS = [
    "HIP",
    "RAICRS",
    "DEICRS",
    "pmRA",
    "pmDE",
    "Plx",
    "e_Plx",
    "Vmag",
    "SpType",
]


def fetch_hipparcos(max_dist_ly: float) -> list[Star]:
    """Fetches the HIPPARCOS stars within ``max_dist_ly`` light-years.

    Positions are the catalogue's ICRS values at epoch J1991.25,
    propagated to J2000.0 with its proper motions. Each entry also
    carries its HIP number in ``_hip_id``. The entries in
    ``SPURIOUS_HIP_IDS`` are left out.

    Returns:
        The entries, or an empty list when the query failed.
    """
    min_parallax = min_parallax_mas(max_dist_ly)
    print(f"[1/4] Querying HIPPARCOS (parallax > {min_parallax} mas)...")
    table = query_catalogue(
        "HIPPARCOS", CATALOGUE, _COLUMNS, Plx=f">{min_parallax}"
    )
    if table is None:
        return []

    ra_j2000, dec_j2000 = propagate_to_j2000(
        float_column(table, "RAICRS"),
        float_column(table, "DEICRS"),
        float_column(table, "pmRA"),
        float_column(table, "pmDE"),
        float_column(table, "Plx"),
        HIPPARCOS_EPOCH_JD,
    )
    stars = []
    for i, row in enumerate(table):
        distance_ly = row_distance_ly(row, "Plx", "e_Plx")
        hip_id = int(row["HIP"])
        if distance_ly is None or hip_id in SPURIOUS_HIP_IDS:
            continue
        magnitude = magnitude_cell(row["Vmag"])
        spectral_type = text_cell(row["SpType"])
        star = catalogue_entry(
            name=HIP_COMMON_NAMES.get(hip_id, f"HIP {hip_id}"),
            distance_ly=distance_ly,
            spectral_type=spectral_type,
            magnitude=magnitude,
            band="V",
            ra_deg=ra_j2000[i],
            dec_deg=dec_j2000[i],
            source="hipparcos",
            catalogue_id=str(hip_id),
        )
        star["_hip_id"] = hip_id
        stars.append(star)

    print(f"  Found {len(stars)} stars")
    return stars
