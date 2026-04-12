#!/usr/bin/env python3
"""
update_eclipses.py -- Refresh eclipses.json from NASA's Five Millennium Catalog.

Scrapes solar and lunar eclipse dates from NASA GSFC, validates the
data, and writes data/eclipses.json. No external dependencies beyond
the Python standard library.

Run locally whenever you want fresh data, then commit and push:

    python tools/update_eclipses.py
    git add data/eclipses.json
    git commit -m "Refresh eclipse catalogue"
    git push
"""

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
START_YEAR = 1900
END_YEAR = 2100

# NASA GSFC catalogue pages. Each century page covers a 100-year span.
# We fetch the 1801-1900 pages to pick up eclipses in the year 1900.
_SOLAR_URLS = [
    "https://eclipse.gsfc.nasa.gov/SEcat5/SE1801-1900.html",
    "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html",
    "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
]
_LUNAR_URLS = [
    "https://eclipse.gsfc.nasa.gov/LEcat5/LE1801-1900.html",
    "https://eclipse.gsfc.nasa.gov/LEcat5/LE1901-2000.html",
    "https://eclipse.gsfc.nasa.gov/LEcat5/LE2001-2100.html",
]

# Regex for "YYYY Mon DD" dates in the pre-formatted catalogue text.
_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_DATE_RE = re.compile(
    r"(\d{4})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+(\d{1,2})"
)

# Known eclipses that MUST appear (sanity check).
_KNOWN_SOLAR = [
    date(2024, 4, 8),    # Total, North America
    date(2017, 8, 21),   # Total, USA
    date(1999, 8, 11),   # Total, Europe
    date(2023, 10, 14),  # Annular
    date(1979, 2, 26),   # Total
]
_KNOWN_LUNAR = [
    date(2022, 11, 8),   # Total
    date(2019, 1, 21),   # Total
    date(2018, 1, 31),   # Total "super blue blood moon"
    date(2000, 1, 21),   # Total
]


# ---------------------------------------------------------------------------
# Fetching and parsing
# ---------------------------------------------------------------------------
def fetch_page(url: str) -> str:
    """Fetch a URL and return the decoded text.

    Args:
        url: Fully-qualified URL to fetch.

    Returns:
        The response body decoded as UTF-8.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "YourFirstLight-EclipseUpdater/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


_PRE_RE = re.compile(
    r"<pre>(.*?)</pre>", re.DOTALL | re.IGNORECASE,
)


def extract_dates(html: str) -> list[date]:
    """Extract YYYY Mon DD dates from ``<pre>`` blocks only.

    Scoping to ``<pre>`` blocks avoids false positives from
    dates in page headers, footers, or navigation elements.

    Args:
        html: Raw HTML page content.

    Returns:
        A list of ``date`` objects found within ``<pre>`` tags.
    """
    dates = []
    for pre_block in _PRE_RE.findall(html):
        for m in _DATE_RE.finditer(pre_block):
            year = int(m.group(1))
            month = _MONTHS[m.group(2)]
            day = int(m.group(3))
            try:
                dates.append(date(year, month, day))
            except ValueError:
                continue  # skip malformed dates
    return dates


def fetch_eclipse_dates(
    urls: list[str],
    label: str,
) -> list[date]:
    """Fetch multiple catalogue pages and return sorted, filtered dates.

    Args:
        urls: NASA catalogue page URLs to scrape.
        label: Human-readable label for logging (e.g. ``"Solar"``).

    Returns:
        Deduplicated, sorted dates within the configured year range.
    """
    all_dates: list[date] = []
    for url in urls:
        print(f"  Fetching {url.split('/')[-1]}...")
        try:
            html = fetch_page(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"    WARNING: Failed to fetch {url}: {e}")
            continue
        page_dates = extract_dates(html)
        print(f"    Extracted {len(page_dates)} dates")
        all_dates.extend(page_dates)

    # Filter to target range and deduplicate
    filtered = sorted({
        d for d in all_dates
        if START_YEAR <= d.year <= END_YEAR
    })
    print(f"  {label}: {len(filtered)} dates in "
          f"{START_YEAR}-{END_YEAR}")
    return filtered


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(
    solar: list[date],
    lunar: list[date],
) -> list[str]:
    """Run integrity checks on the scraped eclipse catalogues.

    Args:
        solar: Sorted solar eclipse dates.
        lunar: Sorted lunar eclipse dates.

    Returns:
        A list of error messages.  An empty list means the data
        is clean and ready to write.
    """
    errors: list[str] = []

    # Sorted
    if solar != sorted(solar):
        errors.append("Solar dates are not sorted")
    if lunar != sorted(lunar):
        errors.append("Lunar dates are not sorted")

    # No duplicates
    if len(solar) != len(set(solar)):
        errors.append("Solar dates contain duplicates")
    if len(lunar) != len(set(lunar)):
        errors.append("Lunar dates contain duplicates")

    # No overlap (a date can't be both solar and lunar)
    overlap = set(solar) & set(lunar)
    if overlap:
        errors.append(
            f"{len(overlap)} date(s) appear in both "
            f"solar and lunar: {sorted(overlap)[:5]}"
        )

    # Minimum interval: consecutive same-type eclipses must be
    # >= 25 days apart (synodic month is 29.5 days).
    for i in range(len(solar) - 1):
        gap = (solar[i + 1] - solar[i]).days
        if gap < 25:
            errors.append(
                f"Solar eclipses {solar[i]} and "
                f"{solar[i + 1]} are only {gap} days "
                f"apart (minimum ~29.5)"
            )
    for i in range(len(lunar) - 1):
        gap = (lunar[i + 1] - lunar[i]).days
        if gap < 25:
            errors.append(
                f"Lunar eclipses {lunar[i]} and "
                f"{lunar[i + 1]} are only {gap} days "
                f"apart (minimum ~29.5)"
            )

    # Every year 1900-2100 has at least 2 solar eclipses
    solar_by_year: dict[int, int] = {}
    for d in solar:
        solar_by_year[d.year] = solar_by_year.get(d.year, 0) + 1
    for y in range(START_YEAR, END_YEAR + 1):
        count = solar_by_year.get(y, 0)
        if count < 2:
            errors.append(
                f"Year {y} has only {count} solar eclipse(s) "
                f"(expected >= 2)"
            )

    # Known reference eclipses present
    solar_set = set(solar)
    for d in _KNOWN_SOLAR:
        if d not in solar_set:
            errors.append(f"Known solar eclipse {d} is missing")

    lunar_set = set(lunar)
    for d in _KNOWN_LUNAR:
        if d not in lunar_set:
            errors.append(f"Known lunar eclipse {d} is missing")

    # Count sanity (roughly 228 solar + 230 lunar per century)
    if not (440 <= len(solar) <= 470):
        errors.append(
            f"Solar count {len(solar)} outside expected "
            f"range 440-470"
        )
    if not (440 <= len(lunar) <= 470):
        errors.append(
            f"Lunar count {len(lunar)} outside expected "
            f"range 440-470"
        )

    return errors


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------
def write_eclipses(solar: list[date], lunar: list[date]) -> None:
    """Write the eclipse catalogue to ``data/eclipses.json``.

    Args:
        solar: Validated solar eclipse dates.
        lunar: Validated lunar eclipse dates.
    """
    output = {
        "source": (
            "NASA Five Millennium Catalog of Eclipses "
            "(eclipse.gsfc.nasa.gov)"
        ),
        "range": f"{START_YEAR}-01-01 to {END_YEAR}-12-31",
        "generated": date.today().isoformat(),
        "counts": {
            "solar": len(solar),
            "lunar": len(lunar),
            "total": len(solar) + len(lunar),
        },
        "solarEclipses": [d.isoformat() for d in solar],
        "lunarEclipses": [d.isoformat() for d in lunar],
    }

    output_path = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "eclipses.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(solar) + len(lunar)} eclipses "
          f"to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Fetch, validate, and write the eclipse catalogue."""
    print("=" * 60)
    print("Your First Light -- Eclipse Catalogue Updater")
    print("=" * 60)
    print()

    print("[1/2] Fetching solar eclipses...")
    solar = fetch_eclipse_dates(_SOLAR_URLS, "Solar")

    print()
    print("[2/2] Fetching lunar eclipses...")
    lunar = fetch_eclipse_dates(_LUNAR_URLS, "Lunar")

    # Validate before writing
    errors = validate(solar, lunar)
    if errors:
        print(f"\nERROR: {len(errors)} validation failure(s):")
        for e in errors:
            print(f"  - {e}")
        print("\nData NOT written. Fix the issues above "
              "before retrying.")
        sys.exit(1)

    print("\nValidation passed")
    write_eclipses(solar, lunar)

    # Summary
    print("\nSummary:")
    print(f"  Solar eclipses: {len(solar)}")
    print(f"  Lunar eclipses: {len(lunar)}")
    print(f"  Total: {len(solar) + len(lunar)}")

    print()
    print("Done! Now commit and push:")
    print("  git add data/eclipses.json")
    print('  git commit -m "Refresh eclipse catalogue"')
    print("  git push")


if __name__ == "__main__":
    main()
