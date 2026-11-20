"""Writing data/stars.json."""

import json
import os
from pathlib import Path

from tools.updaters.stars.entry import Star, sources_of

STARS_PATH = Path(__file__).resolve().parents[3] / "data" / "stars.json"


def write_stars(stars: list[Star], output_path: Path | None = None) -> bool:
    """Sorts the catalogue by distance and writes it.

    The file is written to a temporary sibling and moved into place, so
    an interrupted run never leaves a truncated catalogue. Nothing is
    written when the content is what the file already holds, so an
    automated run can tell "refreshed" from "changed".

    Args:
        stars: The validated catalogue; sorted in place.
        output_path: Where to write; ``STARS_PATH`` when omitted.

    Returns:
        Whether the file on disk changed.
    """
    stars.sort(key=lambda s: (s["distance_ly"], s["name"]))
    clean = [_written_fields(s) for s in stars]

    if output_path is None:
        output_path = STARS_PATH
    payload = json.dumps(clean, indent=4)

    if output_path.exists():
        try:
            unchanged = output_path.read_text(encoding="utf-8") == payload
        except OSError:
            unchanged = False
        if unchanged:
            print(
                f"\n{output_path.name} unchanged "
                f"({len(clean)} stars); not rewritten"
            )
            return False

    tmp_path = output_path.with_name(output_path.name + ".tmp")
    # Without newline="\n", Windows would write CRLF and the file would
    # differ between platforms.
    tmp_path.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp_path, output_path)

    print(f"\nWrote {len(clean)} stars to {output_path}")
    return True


def _written_fields(s: Star) -> Star:
    return {
        "name": s["name"],
        "distance_ly": s["distance_ly"],
        "spectral_type": s["spectral_type"],
        "apparent_magnitude": s["apparent_magnitude"],
        "magnitude_band": s.get("magnitude_band"),
        "known_exoplanets": s["known_exoplanets"],
        "ra_deg": s.get("ra_deg"),
        "dec_deg": s.get("dec_deg"),
        # The catalogue the distance came from.
        "source": (
            s.get("_dist_source")
            or s.get("_source")
            or s.get("source")
            or "curated"
        ),
        # Every catalogue the entry drew from, so the duplicate check
        # can tell a real pair (a shared source) from one star listed
        # twice in the written file just as it does in memory.
        "sources": sorted(sources_of(s)) or ["curated"],
    }
