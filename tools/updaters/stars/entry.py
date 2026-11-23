"""Star entries: the dict every stage of the updater passes along.

An entry carries the fields written to data/stars.json plus private
bookkeeping keys (leading underscore) that only the updater reads:

- ``_source``: the catalogue the entry came from.
- ``_pos_source``: the catalogue its position came from.
- ``_dist_source``: the catalogue its distance came from, once a merge
  has adopted another catalogue's distance.
- ``_merged_sources``: every catalogue merged into it.
- ``_spectral_types``: the spectral type of each catalogue merged into
  it, in merge order.
- ``_catalogue_id``: the identifier in its own catalogue.
- ``_hip_id``: its HIPPARCOS number, when it has one.
- ``_gaia_id``: its Gaia DR3 source ID, when it has one. A HIPPARCOS
  entry carries the one Gaia DR3 matched to it.
- ``_gliese_system``: the Gliese designation of the multiple system it
  is a component of, such as ``"Gl 559"``.
- ``_catalogue_ra``, ``_catalogue_dec``: where the catalogues put it
  before an override replaced the position.
"""

from typing import Any

import numpy as np

Star = dict[str, Any]

DISTANCE_DECIMALS = 4
POSITION_DECIMALS = 4
MAGNITUDE_DECIMALS = 2

# Prefixes of catalogue designations, as opposed to common names.
_CATALOGUE_ID_PREFIXES = ("HIP ", "Gaia ", "Gl ", "GJ ", "NN ", "Wo ")


def catalogue_entry(
    *,
    name: str,
    distance_ly: float,
    spectral_type: str,
    magnitude: float,
    band: str,
    ra_deg: float,
    dec_deg: float,
    source: str,
    catalogue_id: str,
) -> Star:
    """Builds the entry for one catalogue row, rounded for writing.

    A position with a non-finite coordinate becomes ``None`` in both.
    """
    has_pos = bool(np.isfinite(ra_deg) and np.isfinite(dec_deg))
    return {
        "name": name,
        "distance_ly": round(distance_ly, DISTANCE_DECIMALS),
        "spectral_type": spectral_type,
        "apparent_magnitude": round(magnitude, MAGNITUDE_DECIMALS),
        "magnitude_band": band,
        "known_exoplanets": 0,
        "ra_deg": round(float(ra_deg), POSITION_DECIMALS) if has_pos else None,
        "dec_deg": (
            round(float(dec_deg), POSITION_DECIMALS) if has_pos else None
        ),
        "_source": source,
        "_pos_source": source,
        "_catalogue_id": catalogue_id,
    }


def sources_of(star: Star) -> set[str]:
    """Every catalogue an entry drew from; empty for a curated one.

    Reads the merge bookkeeping on an entry in memory and the
    ``sources`` or ``source`` field on one read back from the file.
    """
    merged = star.get("_merged_sources")
    if merged:
        return set(merged)
    listed = star.get("sources")
    if listed:
        return set(listed)
    src = star.get("_source") or star.get("source")
    return {src} if src else set()


def is_catalogue_id(name: str) -> bool:
    """Whether a name is a catalogue designation, such as ``"HIP 1"``."""
    return name.startswith(_CATALOGUE_ID_PREFIXES)
