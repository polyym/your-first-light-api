#!/usr/bin/env python3
"""
update_data.py -- Refresh all data files from upstream sources.

Single entry point that runs every updater in tools/updaters/.
Checks dependencies before starting, runs each updater as a
subprocess, records which data files actually changed, and
maintains data/manifest.json (source, entry counts, and the
date each file last changed).

Usage:
    python tools/update_data.py          # update everything
    python tools/update_data.py stars    # update only stars
    python tools/update_data.py eclipses # update only eclipses

Missing dependencies are reported together with the exact
install command; nothing is ever installed implicitly.

Exit codes: 0 on success (whether or not data changed), 1 when
dependencies are missing or any updater fails.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_UPDATERS_DIR = Path(__file__).resolve().parent / "updaters"
_DATA_DIR = _ROOT / "data"
_MANIFEST_PATH = _DATA_DIR / "manifest.json"

# Each updater: (name, script path, required packages, data file)
_UPDATERS = [
    (
        "eclipses",
        _UPDATERS_DIR / "update_eclipses.py",
        [],  # stdlib only
        "eclipses.json",
    ),
    (
        "stars",
        _UPDATERS_DIR / "update_stars.py",
        ["astroquery"],
        "stars.json",
    ),
]

_SOURCES = {
    "stars.json": (
        "HIPPARCOS (ESA), Gliese Catalogue of Nearby Stars, "
        "Gaia DR3 (ESA), NASA Exoplanet Archive"
    ),
    "eclipses.json": (
        "NASA Five Millennium Catalog of Eclipses "
        "(eclipse.gsfc.nasa.gov)"
    ),
}


def _check_deps(packages: list[str]) -> list[str]:
    """Return the names of any packages that are not installed.

    Args:
        packages: Package names to check for availability.

    Returns:
        A list of package names that could not be found.
    """
    missing = []
    for pkg in packages:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    return missing


def _run_updater(name: str, script: Path) -> bool:
    """Run an updater script as a subprocess.

    Args:
        name: Human-readable label for logging.
        script: Path to the updater Python script.

    Returns:
        ``True`` if the script exited with code 0, ``False``
        otherwise.
    """
    print(f"\n{'=' * 60}")
    print(f"  Running: {name}")
    print(f"{'=' * 60}\n", flush=True)

    result = subprocess.run(
        [sys.executable, "-u", str(script)],
        cwd=str(_ROOT),
    )
    return result.returncode == 0


def _file_digest(path: Path) -> str | None:
    """SHA-256 of a file's bytes, or ``None`` if it is absent.

    Args:
        path: File to hash.

    Returns:
        Hex digest string, or ``None``.
    """
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _entry_count(filename: str) -> int:
    """Number of entries in a data file, for the manifest.

    Args:
        filename: Basename of the data file.

    Returns:
        Star count for the star catalogue, total eclipse count
        for the eclipse catalogue.
    """
    data = json.loads(
        (_DATA_DIR / filename).read_text(encoding="utf-8"),
    )
    if filename == "stars.json":
        return len(data)
    return (
        len(data["solarEclipses"]) + len(data["lunarEclipses"])
    )


def _load_manifest() -> dict:
    """Read data/manifest.json, tolerating absence/corruption.

    Returns:
        The parsed manifest, or an empty dict.
    """
    try:
        return json.loads(
            _MANIFEST_PATH.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError):
        return {}


def update_manifest(changed: dict[str, bool]) -> bool:
    """Refresh data/manifest.json after a successful run.

    The per-file ``updated`` stamp only moves when that file's
    content actually changed, so a refresh that found nothing
    new leaves the manifest untouched and automated runs can
    use ``git diff data/`` as an honest change signal.

    Args:
        changed: Mapping of data file basename to whether this
            run changed it.

    Returns:
        ``True`` when the manifest file itself was rewritten.
    """
    manifest = _load_manifest()
    files = manifest.get("files", {})
    today = datetime.now(timezone.utc).date().isoformat()

    for filename, did_change in changed.items():
        entry = files.get(filename, {})
        entry["source"] = _SOURCES[filename]
        entry["entries"] = _entry_count(filename)
        if did_change or "updated" not in entry:
            entry["updated"] = today
        files[filename] = entry

    payload = json.dumps({"files": files}, indent=2)
    try:
        if (
            _MANIFEST_PATH.read_text(encoding="utf-8")
            == payload
        ):
            return False
    except OSError:
        pass

    tmp_path = _MANIFEST_PATH.with_name(
        _MANIFEST_PATH.name + ".tmp",
    )
    # newline="\n" keeps output byte-identical across platforms
    # (Windows text mode would otherwise write CRLF).
    tmp_path.write_text(payload, encoding="utf-8", newline="\n")
    os.replace(tmp_path, _MANIFEST_PATH)
    return True


def main() -> None:
    """Entry point: check deps, run updaters, update manifest."""
    # Parse optional filter argument
    filter_name = None
    if len(sys.argv) > 1:
        filter_name = sys.argv[1].lower()
        valid = {name for name, _, _, _ in _UPDATERS}
        if filter_name not in valid:
            print(f"Unknown updater: {filter_name!r}")
            print(f"Available: {', '.join(sorted(valid))}")
            sys.exit(1)

    # Select which updaters to run
    to_run = [
        entry for entry in _UPDATERS
        if filter_name is None or entry[0] == filter_name
    ]

    # Report missing dependencies; never install implicitly.
    all_missing: list[str] = []
    for _, _, deps, _ in to_run:
        all_missing.extend(_check_deps(deps))

    if all_missing:
        unique = sorted(set(all_missing))
        print(f"Missing required packages: {', '.join(unique)}")
        print("Install them into the current environment with:")
        print('  pip install -e ".[catalogue]"')
        sys.exit(1)

    # Run each updater, recording whether its data file changed.
    results: dict[str, bool] = {}
    changed: dict[str, bool] = {}
    for name, script, _, data_file in to_run:
        before = _file_digest(_DATA_DIR / data_file)
        results[name] = _run_updater(name, script)
        if results[name]:
            after = _file_digest(_DATA_DIR / data_file)
            changed[data_file] = before != after

    # Summary
    print(f"\n{'=' * 60}")
    print("  Summary")
    print(f"{'=' * 60}")
    all_ok = True
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name:12s} {status}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nSome updaters failed. Check output above.")
        sys.exit(1)

    update_manifest(changed)

    if any(changed.values()):
        updated = sorted(
            f for f, did in changed.items() if did
        )
        print(f"\nData changed: {', '.join(updated)}")
        print("Review the diff under data/ and commit it")
        print("(the scheduled workflow opens a pull request).")
    else:
        print("\nAll data already up to date; nothing to commit.")


if __name__ == "__main__":
    main()
