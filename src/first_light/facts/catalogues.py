"""The star and eclipse catalogues in data/, loaded once at import.

tools/update_data.py validates all three files before it writes them, so
they are trusted here. The manifest is optional: without it /health
leaves out its data_updated field.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class Star(TypedDict):
    """One entry of data/stars.json."""

    name: str
    distance_ly: float
    # Empty when no catalogue gives a type.
    spectral_type: str
    apparent_magnitude: float
    # "V" or "G"; None when the band is unknown.
    magnitude_band: str | None
    known_exoplanets: int
    # J2000; None for a star with no usable position.
    ra_deg: float | None
    dec_deg: float | None
    # The catalogue the distance came from, then every catalogue the
    # entry drew on. Only the updater reads them.
    source: str
    sources: list[str]


def _read(name: str) -> Any:
    with open(DATA_DIR / name, encoding="utf-8") as file:
        return json.load(file)


NEARBY_STARS: list[Star] = _read("stars.json")
_eclipses = _read("eclipses.json")
SOLAR_ECLIPSE_DATES = tuple(
    date.fromisoformat(day) for day in _eclipses["solarEclipses"]
)
LUNAR_ECLIPSE_DATES = tuple(
    date.fromisoformat(day) for day in _eclipses["lunarEclipses"]
)
DATA_MANIFEST: dict[str, Any] = (
    _read("manifest.json") if (DATA_DIR / "manifest.json").exists() else {}
)
