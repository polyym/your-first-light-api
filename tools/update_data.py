#!/usr/bin/env python3
"""
update_data.py -- Refresh all data files from upstream sources.

Single entry point that runs every updater in tools/updaters/.
Checks dependencies before starting, runs each updater as a
subprocess, and reports combined status.

Usage:
    python tools/update_data.py          # update everything
    python tools/update_data.py stars    # update only stars
    python tools/update_data.py eclipses # update only eclipses
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_UPDATERS_DIR = Path(__file__).resolve().parent / "updaters"

# Each updater: (name, script path, required packages)
_UPDATERS = [
    (
        "eclipses",
        _UPDATERS_DIR / "update_eclipses.py",
        [],  # stdlib only
    ),
    (
        "stars",
        _UPDATERS_DIR / "update_stars.py",
        ["astroquery"],
    ),
]


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


def main() -> None:
    """Entry point: parse arguments, install deps, and run updaters."""
    # Parse optional filter argument
    filter_name = None
    if len(sys.argv) > 1:
        filter_name = sys.argv[1].lower()
        valid = {name for name, _, _ in _UPDATERS}
        if filter_name not in valid:
            print(f"Unknown updater: {filter_name!r}")
            print(f"Available: {', '.join(sorted(valid))}")
            sys.exit(1)

    # Select which updaters to run
    to_run = [
        (name, script, deps) for name, script, deps in _UPDATERS
        if filter_name is None or name == filter_name
    ]

    # Check and auto-install missing dependencies
    all_missing: list[str] = []
    for _, _, deps in to_run:
        all_missing.extend(_check_deps(deps))

    if all_missing:
        unique = sorted(set(all_missing))
        print(f"Installing missing dependencies: "
              f"{', '.join(unique)}\n", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "-e", ".[catalogue]", "--quiet"],
            cwd=str(_ROOT),
        )
        if result.returncode != 0:
            print("Failed to install dependencies.")
            sys.exit(1)

    # Run each updater
    results: dict[str, bool] = {}
    for name, script, _ in to_run:
        results[name] = _run_updater(name, script)

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

    if all_ok:
        print("\nAll data updated. Commit with:")
        print("  git add data/")
        print('  git commit -m "Refresh data catalogues"')
    else:
        print("\nSome updaters failed. Check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
