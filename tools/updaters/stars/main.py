"""The star catalogue updater's steps, in order."""

import sys
from typing import NoReturn

from tools.updaters.stars.curated import EXTRA_STARS
from tools.updaters.stars.entry import Star
from tools.updaters.stars.exoplanets import (
    fetch_exoplanet_counts,
    match_exoplanets,
)
from tools.updaters.stars.gaia import fetch_gaia
from tools.updaters.stars.gliese import fetch_gliese
from tools.updaters.stars.hipparcos import fetch_hipparcos
from tools.updaters.stars.merge import (
    add_extra_stars,
    apply_overrides,
    dedup_by_coordinates,
    dedup_by_name,
    merge_catalogues,
)
from tools.updaters.stars.photometry import (
    fix_spectral_types,
    remove_unknown_magnitudes,
)
from tools.updaters.stars.validate import (
    MAX_RADIUS_LY,
    check_fetch_counts,
    check_reference_positions,
    validate_catalogue,
)
from tools.updaters.stars.write import write_stars

# The closing summary counts the stars within each of these distances.
SUMMARY_RADII_LY = (15, 25, 50)

_UPSTREAM_ADVICE = "Upstream sources are unavailable or degraded; retry later."
_PIPELINE_ADVICE = "Fix the issues above before retrying."


def main() -> None:
    """Fetches, merges, corrects, validates and writes the catalogue.

    Exits with status 1, leaving data/stars.json as it was, when a
    fetch or the validation fails.
    """
    print("=" * 60)
    print("Your First Light -- Star Catalogue Updater")
    print("=" * 60)
    print()

    stars = _merge(*_fetch_catalogues())
    print(f"  Applied overrides to {apply_overrides(stars)} stars")
    _add_exoplanet_counts(stars)

    errors = validate_catalogue(stars)
    if errors:
        _fail(errors, "validation", _PIPELINE_ADVICE)
    print("\nValidation passed")
    changed = write_stars(stars)
    _print_summary(stars, changed)


def _fetch_catalogues() -> list[list[Star]]:
    """Fetches HIPPARCOS, Gliese and Gaia, in the order they merge.

    A source that came back empty or thin, or with its reference stars
    out of place, would give a catalogue that looks plausible while
    missing thousands of stars or listing them twice, so the run stops.
    """
    fetched = {
        "hipparcos": fetch_hipparcos(MAX_RADIUS_LY),
        "gliese": fetch_gliese(MAX_RADIUS_LY),
        "gaia": fetch_gaia(MAX_RADIUS_LY),
    }
    errors = check_fetch_counts({k: len(v) for k, v in fetched.items()})
    for source, stars in fetched.items():
        errors += check_reference_positions(stars, source)
    if errors:
        _fail(errors, "fetch", _UPSTREAM_ADVICE)
    return list(fetched.values())


def _merge(*catalogues: list[Star]) -> list[Star]:
    """Merges the catalogues, adds the extra stars and cleans up."""
    print("\nMerging catalogues...")
    stars = merge_catalogues(*catalogues)
    print(f"  Merged to {len(stars)} unique stars")

    added, replaced = add_extra_stars(stars, EXTRA_STARS)
    print(f"  Added {added}, replaced {replaced} from EXTRA_STARS")
    removed = dedup_by_coordinates(stars, EXTRA_STARS)
    print(f"  Removed {removed} catalogue duplicates of EXTRA_STARS entries")

    deduped = dedup_by_name(stars)
    mag_removed = remove_unknown_magnitudes(stars)
    types = fix_spectral_types(stars)
    print(
        f"  Auto-fix: {deduped} duplicates removed, "
        f"{mag_removed} no-magnitude entries dropped"
    )
    print(
        f"  Spectral types: {types.normalised} normalised; of those the "
        f"star's magnitude rules out, {types.replaced} replaced by another "
        f"catalogue's, {types.trimmed} cut back to their temperature class "
        f"and {types.cleared} cleared"
    )
    return stars


def _add_exoplanet_counts(stars: list[Star]) -> None:
    """Sets planet counts from the archive, after the overrides.

    The archive's count wins for every star it lists, so a refresh
    keeps the best-known stars current; a curated count stays only
    where the archive does not list the star. A failed or thin
    archive answer stops the run: carrying on would zero nearly
    every planet count while every other check passed.
    """
    exo_counts = fetch_exoplanet_counts()
    errors = check_fetch_counts({"exoplanet_archive": len(exo_counts)})
    if errors:
        _fail(errors, "fetch", _UPSTREAM_ADVICE)
    matched = match_exoplanets(stars, exo_counts)
    print(f"  Matched exoplanets to {matched} stars")


def _fail(errors: list[str], kind: str, advice: str) -> NoReturn:
    print(f"\nERROR: {len(errors)} {kind} failure(s):")
    for e in errors:
        print(f"  - {e}")
    print(f"\nData NOT written. {advice}")
    sys.exit(1)


def _print_summary(stars: list[Star], changed: bool) -> None:
    print("\nSummary:")
    for radius_ly in SUMMARY_RADII_LY:
        within = sum(1 for s in stars if s["distance_ly"] <= radius_ly)
        print(f"  Stars within {radius_ly} ly: {within}")
    print(f"  Total stars: {len(stars)}")
    planets = sum(s["known_exoplanets"] for s in stars)
    print(f"  Total known exoplanets: {planets}")

    print()
    if changed:
        print("Done! Review the diff, then commit data/stars.json")
        print("(the scheduled workflow does this via a pull request).")
    else:
        print("Done! Catalogue already up to date.")
