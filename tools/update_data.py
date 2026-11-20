"""Refreshes every data file from its upstream source.

The single entry point for the updaters in tools/updaters/. It checks
their dependencies first, runs each as a subprocess from the repository
root, notes which data files changed and keeps data/manifest.json (each
file's source, entry count and the date it last changed) up to date.
It ends with a short Markdown summary for reviewers: entry counts
before and after, the star names within ``SUMMARY_RADIUS_LY`` that were
added, removed or renamed, and the spectral types and planet counts
there that changed.
When the environment variable named by ``SUMMARY_PATH_ENV`` gives a
path, the summary is also written there, for a scheduled run to use as
its pull request body.

Usage:
    python tools/update_data.py           # update everything
    python tools/update_data.py stars     # update only the stars
    python tools/update_data.py eclipses  # update only the eclipses

Missing dependencies are reported with the command that installs them;
nothing is ever installed implicitly.

Exits with status 0 on success, whether or not data changed, and 1 when
dependencies are missing, data/manifest.json cannot be read as a
manifest or an updater fails.
"""

import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from astropy import units
from astropy.coordinates import angular_separation

_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT / "data"
_MANIFEST_PATH = _DATA_DIR / "manifest.json"

# The environment variable that names where to write the summary.
SUMMARY_PATH_ENV = "DATA_SUMMARY_PATH"
# The summary lists name changes among the stars this close, few enough
# for a reviewer to check each one.
SUMMARY_RADIUS_LY = 30
# A vanished name and a new one this close on the sky are taken as one
# star renamed: HIPPARCOS and Gaia, which place almost every star that
# near, agree on its position far better than this.
RENAME_MAX_SEP_ARCSEC = 20.0


class _Updater(NamedTuple):
    name: str
    # Run as ``python -m <module>`` from the repository root.
    module: str
    # Import names of the packages it needs beyond the app's own.
    packages: list[str]
    data_file: str


_UPDATERS = [
    _Updater("eclipses", "tools.updaters.update_eclipses", [], "eclipses.json"),
    _Updater("stars", "tools.updaters.stars", ["astroquery"], "stars.json"),
]

_SOURCES = {
    "stars.json": (
        "HIPPARCOS (ESA), Gliese Catalogue of Nearby Stars, "
        "Gaia DR3 (ESA), NASA Exoplanet Archive"
    ),
    "eclipses.json": (
        "NASA Five Millennium Catalog of Eclipses (eclipse.gsfc.nasa.gov)"
    ),
}


def _missing_packages(packages: list[str]) -> list[str]:
    """The packages that are not installed."""
    return [pkg for pkg in packages if importlib.util.find_spec(pkg) is None]


def _run_updater(updater: _Updater) -> bool:
    """Runs one updater and reports whether it exited with status 0."""
    print(f"\n{'=' * 60}")
    print(f"  Running: {updater.name}")
    print(f"{'=' * 60}\n", flush=True)

    result = subprocess.run(
        [sys.executable, "-u", "-m", updater.module],
        cwd=str(_ROOT),
    )
    return result.returncode == 0


def _file_digest(path: Path) -> str | None:
    """The SHA-256 of a file's bytes, or ``None`` if it is absent."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_data(filename: str) -> Any:
    """A data file's parsed content, or ``None`` if absent or corrupt."""
    try:
        return json.loads((_DATA_DIR / filename).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _entry_count(filename: str, data: Any) -> int:
    """The number of stars, or of eclipses, in a data file's content."""
    if filename == "stars.json":
        return len(data)
    return len(data["solarEclipses"]) + len(data["lunarEclipses"])


def _generated_date(data: Any) -> str | None:
    """The ``generated`` date a data file records, if it records one."""
    if isinstance(data, dict):
        return data.get("generated")
    return None


def _load_manifest() -> dict[str, Any]:
    """The parsed manifest, or an empty dict if there is none yet.

    Raises:
        ValueError: The manifest is not valid JSON, or not an object
            whose ``files`` is an object of objects. Starting afresh
            would drop the other files' entries and date every file
            today.
    """
    try:
        text = _MANIFEST_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    manifest = json.loads(text)
    shape_error = 'not an object with a "files" object of objects'
    if not isinstance(manifest, dict):
        raise ValueError(shape_error)
    files = manifest.get("files", {})
    if not isinstance(files, dict) or not all(
        isinstance(entry, dict) for entry in files.values()
    ):
        raise ValueError(shape_error)
    return manifest


def update_manifest(changed: dict[str, bool]) -> bool:
    """Brings data/manifest.json up to date after a successful run.

    A file's ``updated`` date moves only when this run changed its
    content, so a run that found nothing new leaves the manifest as it
    was and ``git diff data/`` stays an honest signal of change. A file
    new to the manifest that did not change takes the date it records
    as ``generated``, when it records one, since that is when its
    content last changed.

    Args:
        changed: Whether this run changed each data file, by basename.

    Returns:
        Whether the manifest file itself was rewritten.
    """
    manifest = _load_manifest()
    files = manifest.get("files", {})
    today = datetime.now(UTC).date().isoformat()

    for filename, did_change in changed.items():
        data = _load_data(filename)
        entry = files.get(filename, {})
        entry["source"] = _SOURCES[filename]
        entry["entries"] = _entry_count(filename, data)
        if did_change:
            entry["updated"] = today
        elif "updated" not in entry:
            entry["updated"] = _generated_date(data) or today
        files[filename] = entry

    payload = json.dumps({"files": files}, indent=2)
    try:
        if _MANIFEST_PATH.read_text(encoding="utf-8") == payload:
            return False
    except OSError:
        pass

    tmp_path = _MANIFEST_PATH.with_name(_MANIFEST_PATH.name + ".tmp")
    # Without newline="\n", Windows would write CRLF and the file would
    # differ between platforms.
    tmp_path.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp_path, _MANIFEST_PATH)
    return True


def data_summary(before: dict[str, Any], after: dict[str, Any]) -> str:
    """A short Markdown account of what a run changed, for reviewers.

    Gives each data file's entry count before and after and, when the
    stars were refreshed, the catalogue's known exoplanets before and
    after, the names within ``SUMMARY_RADIUS_LY`` that were added,
    removed or renamed, and the spectral types and planet counts there
    that changed: clients may key their own data on the names, and
    show the class each type gives. Once the static star catalogues
    have been refreshed, planet counts are what changes each month.

    Args:
        before: Each refreshed data file's parsed content before the
            run, by basename; ``None`` for a file that was absent.
        after: The same after the run.
    """
    lines = [
        "## Data refresh summary",
        "",
        "| File | Entries before | Entries after |",
        "| --- | ---: | ---: |",
    ]
    for filename in sorted(after):
        old = _count_text(filename, before.get(filename))
        new = _count_text(filename, after[filename])
        lines.append(f"| {filename} | {old} | {new} |")
    if "stars.json" in after:
        old_stars = before.get("stars.json") or []
        new_stars = after["stars.json"] or []
        lines += [
            "",
            f"Known exoplanets: {_planet_total(old_stars)} before, "
            f"{_planet_total(new_stars)} after.",
            "",
        ]
        lines += _near_star_changes(old_stars, new_stars)
    return "\n".join(lines) + "\n"


def _planet_total(stars: list[dict[str, Any]]) -> int:
    return sum(star["known_exoplanets"] for star in stars)


def _count_text(filename: str, data: Any) -> str:
    return "none" if data is None else str(_entry_count(filename, data))


def _near_star_changes(
    old: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[str]:
    """Summary lines for the changes among the near stars.

    A name gone from the catalogue is paired with a name new to it at
    the same place on the sky, closest first, as a rename; the other
    names that left were removed and the others that joined added. A
    star that only crossed ``SUMMARY_RADIUS_LY`` is listed with its
    distance on both sides. A name near on either side whose spectral
    type or planet count changed is listed with both values, and a
    rename with both types and both planet counts when they differ.
    """
    old_by_name = {s["name"]: s for s in old}
    new_by_name = {s["name"]: s for s in new}
    old_near = {n for n, s in old_by_name.items() if _is_near(s)}
    new_near = {n for n, s in new_by_name.items() if _is_near(s)}
    left = sorted(old_near - new_near)
    joined = sorted(new_near - old_near)
    renamed = _renames(left, joined, old_by_name, new_by_name)
    removed = [n for n in left if n not in renamed.values()]
    added = [n for n in joined if n not in renamed]

    lines = [
        f"Stars within {SUMMARY_RADIUS_LY} ly: {len(old_near)} before, "
        f"{len(new_near)} after."
    ]
    if not (added or removed or renamed):
        lines += [
            "",
            f"No star within {SUMMARY_RADIUS_LY} ly was added, removed "
            f"or renamed.",
        ]
    if added:
        lines += ["", f"Added ({len(added)}):"]
        for n in _by_distance(added, new_by_name):
            lines.append(_star_line(n, new_by_name, old_by_name, "was"))
    if removed:
        lines += ["", f"Removed ({len(removed)}):"]
        for n in _by_distance(removed, old_by_name):
            lines.append(_star_line(n, old_by_name, new_by_name, "now"))
    if renamed:
        lines += ["", f"Renamed ({len(renamed)}):"]
        for n in _by_distance(list(renamed), new_by_name):
            lines.append(
                _rename_line(
                    renamed[n], old_by_name[renamed[n]], n, new_by_name[n]
                )
            )

    near = old_near | new_near
    lines += _value_changes(
        "Spectral type changed", near, old_by_name, new_by_name, _type_text
    )
    lines += _value_changes(
        "Known exoplanets changed",
        near,
        old_by_name,
        new_by_name,
        lambda star: str(star["known_exoplanets"]),
    )
    return lines


def _renames(
    left: list[str],
    joined: list[str],
    old_by_name: dict[str, Any],
    new_by_name: dict[str, Any],
) -> dict[str, str]:
    """Pairs the names that left with the names that joined in their place.

    A name gone from the catalogue and a name new to it, no more than
    ``RENAME_MAX_SEP_ARCSEC`` apart, are one star renamed. The closest
    pairs are taken first, and each name is paired at most once.

    Returns:
        The old name of each renamed star, by its new name.
    """
    pairs = []
    for gone in left:
        for came in joined:
            if gone in new_by_name or came in old_by_name:
                continue
            sep = _sep_arcsec(old_by_name[gone], new_by_name[came])
            if sep <= RENAME_MAX_SEP_ARCSEC:
                pairs.append((sep, gone, came))
    renamed: dict[str, str] = {}
    for _sep, gone, came in sorted(pairs):
        if came not in renamed and gone not in renamed.values():
            renamed[came] = gone
    return renamed


def _rename_line(
    old_name: str,
    old_star: dict[str, Any],
    new_name: str,
    new_star: dict[str, Any],
) -> str:
    """A list line for a renamed star, with its type and planet changes."""
    line = f"- {old_name} -> {new_name}, {new_star['distance_ly']} ly"
    changes = []
    if old_star["spectral_type"] != new_star["spectral_type"]:
        changes.append(f"{_type_text(old_star)} -> {_type_text(new_star)}")
    if old_star["known_exoplanets"] != new_star["known_exoplanets"]:
        changes.append(
            f"planets {old_star['known_exoplanets']} -> "
            f"{new_star['known_exoplanets']}"
        )
    if changes:
        line += f" ({'; '.join(changes)})"
    return line


def _value_changes(
    heading: str,
    names: set[str],
    old_by_name: dict[str, Any],
    new_by_name: dict[str, Any],
    value: Callable[[dict[str, Any]], str],
) -> list[str]:
    """Summary lines for the names on both sides whose value changed."""
    changed = [
        n
        for n in names
        if n in old_by_name
        and n in new_by_name
        and value(old_by_name[n]) != value(new_by_name[n])
    ]
    if not changed:
        return []
    lines = ["", f"{heading} ({len(changed)}):"]
    for n in _by_distance(changed, new_by_name):
        distance_ly = new_by_name[n]["distance_ly"]
        old, new = value(old_by_name[n]), value(new_by_name[n])
        lines.append(f"- {n}, {distance_ly} ly: {old} -> {new}")
    return lines


def _type_text(star: dict[str, Any]) -> str:
    return star["spectral_type"] or "no type"


def _is_near(star: dict[str, Any]) -> bool:
    distance_ly: float = star["distance_ly"]
    return distance_ly <= SUMMARY_RADIUS_LY


def _by_distance(names: list[str], stars: dict[str, Any]) -> list[str]:
    return sorted(names, key=lambda n: (stars[n]["distance_ly"], n))


def _star_line(
    name: str, here: dict[str, Any], there: dict[str, Any], there_word: str
) -> str:
    """A list line with a star's distance, and its other one if it has one.

    ``there_word`` introduces the distance in ``there``, the catalogue
    from the other side of the run.
    """
    line = f"- {name}, {here[name]['distance_ly']} ly"
    if name in there:
        line += f" ({there_word} {there[name]['distance_ly']} ly)"
    return line


def _sep_arcsec(a: dict[str, Any], b: dict[str, Any]) -> float:
    """The angle between two entries; infinite when either has no place."""
    if None in (a["ra_deg"], a["dec_deg"], b["ra_deg"], b["dec_deg"]):
        return math.inf
    sep = angular_separation(
        a["ra_deg"] * units.deg,
        a["dec_deg"] * units.deg,
        b["ra_deg"] * units.deg,
        b["dec_deg"] * units.deg,
    )
    return float(sep.to_value(units.arcsec))


def _write_summary(summary: str) -> None:
    """Writes the summary where ``SUMMARY_PATH_ENV`` says, if it is set."""
    path = os.environ.get(SUMMARY_PATH_ENV)
    if path:
        Path(path).write_text(summary, encoding="utf-8", newline="\n")
        print(f"Summary written to {path}")


def main() -> None:
    """Checks dependencies, runs the updaters and updates the manifest."""
    to_run = _UPDATERS
    if len(sys.argv) > 1:
        filter_name = sys.argv[1].lower()
        valid = {u.name for u in _UPDATERS}
        if filter_name not in valid:
            print(f"Unknown updater: {filter_name!r}")
            print(f"Available: {', '.join(sorted(valid))}")
            sys.exit(1)
        to_run = [u for u in _UPDATERS if u.name == filter_name]

    missing = sorted(
        {pkg for u in to_run for pkg in _missing_packages(u.packages)}
    )
    if missing:
        print(f"Missing required packages: {', '.join(missing)}")
        print("Install them into the project environment with:")
        print("  uv sync --group catalogue")
        sys.exit(1)

    # Checked before the updaters run, so a corrupt manifest stops the
    # run with the data files as they were.
    try:
        _load_manifest()
    except ValueError as e:
        print(f"{_MANIFEST_PATH} is not a usable manifest: {e}")
        sys.exit(1)

    before = {u.data_file: _load_data(u.data_file) for u in to_run}
    results: dict[str, bool] = {}
    changed: dict[str, bool] = {}
    for updater in to_run:
        data_path = _DATA_DIR / updater.data_file
        digest_before = _file_digest(data_path)
        results[updater.name] = _run_updater(updater)
        if results[updater.name]:
            changed[updater.data_file] = digest_before != _file_digest(
                data_path
            )

    print(f"\n{'=' * 60}")
    print("  Summary")
    print(f"{'=' * 60}")
    for name, ok in results.items():
        print(f"  {name:12s} {'OK' if ok else 'FAILED'}")

    if not all(results.values()):
        print("\nSome updaters failed. Check output above.")
        sys.exit(1)

    update_manifest(changed)

    summary = data_summary(before, {f: _load_data(f) for f in before})
    print(f"\n{summary}")
    _write_summary(summary)

    updated = sorted(f for f, did in changed.items() if did)
    if updated:
        print(f"\nData changed: {', '.join(updated)}")
        print("Review the diff under data/ and commit it")
        print("(the scheduled workflow opens a pull request).")
    else:
        print("\nAll data already up to date; nothing to commit.")


if __name__ == "__main__":
    main()
