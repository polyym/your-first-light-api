"""The eclipse catalogue updater, which rebuilds data/eclipses.json.

It scrapes solar and lunar eclipse dates from NASA GSFC's Five
Millennium Catalog, retrying each page, validates them and writes the
file, using only the standard library. The write is atomic and happens
only when the dates changed; a failed check exits non-zero and leaves
the file as it was.

Run it from the repository root, normally through the single entry
point that also maintains data/manifest.json:

    python tools/update_data.py eclipses

or on its own as ``python -m tools.updaters.update_eclipses``.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, date, datetime
from functools import partial
from itertools import pairwise
from pathlib import Path

from tools.updaters.retry import with_retries

START_YEAR = 1900
END_YEAR = 2100

ECLIPSES_PATH = Path(__file__).resolve().parents[2] / "data" / "eclipses.json"
SOURCE = "NASA Five Millennium Catalog of Eclipses (eclipse.gsfc.nasa.gov)"

# One page per century. The 1801-1900 pages hold the eclipses of 1900.
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
USER_AGENT = "YourFirstLight-EclipseUpdater/1.0"
FETCH_TIMEOUT_SECONDS = 30

# Eclipses of one kind are a synodic month (29.5 days) or more apart.
MIN_SAME_KIND_GAP_DAYS = 25
# Every year has at least two eclipses of each kind (counting penumbral
# lunar eclipses). Checking each year catches one century page failing
# to fetch, which barely moves the totals.
MIN_ECLIPSES_PER_YEAR = 2
# About 228 solar and 230 lunar eclipses happen each century, so the
# years from START_YEAR to END_YEAR hold about 460 of each.
MIN_ECLIPSES_PER_KIND = 440
MAX_ECLIPSES_PER_KIND = 470

_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
# A "YYYY Mon DD" date in the catalogue's pre-formatted text.
_DATE_RE = re.compile(
    r"(\d{4})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+(\d{1,2})"
)
_PRE_RE = re.compile(r"<pre>(.*?)</pre>", re.DOTALL | re.IGNORECASE)

# Eclipses that must appear, as a check on the scrape.
_KNOWN_SOLAR = [
    date(2024, 4, 8),  # Total, North America
    date(2017, 8, 21),  # Total, USA
    date(1999, 8, 11),  # Total, Europe
    date(2023, 10, 14),  # Annular
    date(1979, 2, 26),  # Total
]
_KNOWN_LUNAR = [
    date(2022, 11, 8),  # Total
    date(2019, 1, 21),  # Total
    date(2018, 1, 31),  # Total, "super blue blood moon"
    date(2000, 1, 21),  # Total
]


def fetch_page(url: str) -> str:
    """Fetches a page and decodes it as UTF-8."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
        body: bytes = resp.read()
    return body.decode("utf-8", errors="replace")


def extract_dates(html: str) -> list[date]:
    """Finds the "YYYY Mon DD" dates in a page's ``<pre>`` blocks.

    Only ``<pre>`` blocks hold the catalogue; dates in headers, footers
    and navigation are not eclipses. Impossible dates are skipped.
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
                continue
    return dates


def fetch_eclipse_dates(urls: list[str], label: str) -> list[date]:
    """Scrapes catalogue pages for eclipse dates.

    A page that fails every fetch attempt is reported and skipped;
    validation then catches the missing years.

    Args:
        urls: The catalogue pages of one kind of eclipse.
        label: That kind in the log, such as ``"Solar"``.

    Returns:
        The distinct dates from START_YEAR to END_YEAR, in order.
    """
    all_dates: list[date] = []
    for url in urls:
        page = url.split("/")[-1]
        print(f"  Fetching {page}...")
        try:
            html = with_retries(partial(fetch_page, url), page)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"    WARNING: Failed to fetch {url}: {e}")
            continue
        page_dates = extract_dates(html)
        print(f"    Extracted {len(page_dates)} dates")
        all_dates.extend(page_dates)

    filtered = sorted(
        {d for d in all_dates if START_YEAR <= d.year <= END_YEAR}
    )
    print(f"  {label}: {len(filtered)} dates in {START_YEAR}-{END_YEAR}")
    return filtered


def validate(solar: list[date], lunar: list[date]) -> list[str]:
    """Checks the scraped catalogues before they are written.

    Returns:
        The error messages; an empty list means the data can be
        written.
    """
    kinds = (("Solar", solar), ("Lunar", lunar))
    errors: list[str] = []

    for label, dates in kinds:
        if dates != sorted(dates):
            errors.append(f"{label} dates are not sorted")
    for label, dates in kinds:
        if len(dates) != len(set(dates)):
            errors.append(f"{label} dates contain duplicates")

    overlap = set(solar) & set(lunar)
    if overlap:
        errors.append(
            f"{len(overlap)} date(s) appear in both "
            f"solar and lunar: {sorted(overlap)[:5]}"
        )

    for label, dates in kinds:
        for earlier, later in pairwise(dates):
            gap = (later - earlier).days
            if gap < MIN_SAME_KIND_GAP_DAYS:
                errors.append(
                    f"{label} eclipses {earlier} and {later} are only "
                    f"{gap} days apart (minimum ~29.5)"
                )

    per_year = [
        (label, Counter(d.year for d in dates)) for label, dates in kinds
    ]
    for year in range(START_YEAR, END_YEAR + 1):
        for label, by_year in per_year:
            count = by_year[year]
            if count < MIN_ECLIPSES_PER_YEAR:
                errors.append(
                    f"Year {year} has only {count} {label.lower()} "
                    f"eclipse(s) (expected >= {MIN_ECLIPSES_PER_YEAR})"
                )

    for label, dates, known in (
        ("solar", solar, _KNOWN_SOLAR),
        ("lunar", lunar, _KNOWN_LUNAR),
    ):
        present = set(dates)
        for d in known:
            if d not in present:
                errors.append(f"Known {label} eclipse {d} is missing")

    for label, dates in kinds:
        if not (MIN_ECLIPSES_PER_KIND <= len(dates) <= MAX_ECLIPSES_PER_KIND):
            errors.append(
                f"{label} count {len(dates)} outside expected range "
                f"{MIN_ECLIPSES_PER_KIND}-{MAX_ECLIPSES_PER_KIND}"
            )

    return errors


def write_eclipses(
    solar: list[date],
    lunar: list[date],
    output_path: Path | None = None,
) -> bool:
    """Writes eclipse dates that passed ``validate``.

    The file is written to a temporary sibling and moved into place, so
    an interrupted run never leaves a truncated catalogue. Nothing is
    written when the dates are those the file already holds; its
    ``generated`` stamp then stays as it was, so refresh runs do not
    churn the file.

    Args:
        solar: Solar eclipse dates, in order.
        lunar: Lunar eclipse dates, in order.
        output_path: Where to write; ``ECLIPSES_PATH`` when omitted.

    Returns:
        Whether the file on disk changed.
    """
    output = {
        "source": SOURCE,
        "range": f"{START_YEAR}-01-01 to {END_YEAR}-12-31",
        # The UTC date, as the manifest dates a change, on any machine.
        "generated": datetime.now(UTC).date().isoformat(),
        "counts": {
            "solar": len(solar),
            "lunar": len(lunar),
            "total": len(solar) + len(lunar),
        },
        "solarEclipses": [d.isoformat() for d in solar],
        "lunarEclipses": [d.isoformat() for d in lunar],
    }

    if output_path is None:
        output_path = ECLIPSES_PATH

    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if (
            existing is not None
            and existing.get("solarEclipses") == output["solarEclipses"]
            and existing.get("lunarEclipses") == output["lunarEclipses"]
        ):
            print(
                f"\n{output_path.name} unchanged "
                f"({len(solar) + len(lunar)} eclipses); "
                f"not rewritten"
            )
            return False

    tmp_path = output_path.with_name(output_path.name + ".tmp")
    # Without newline="\n", Windows would write CRLF and the file would
    # differ between platforms.
    tmp_path.write_text(
        json.dumps(output, indent=2), encoding="utf-8", newline="\n"
    )
    os.replace(tmp_path, output_path)

    print(f"\nWrote {len(solar) + len(lunar)} eclipses to {output_path}")
    return True


def main() -> None:
    """Fetches, validates and writes the eclipse catalogue.

    Exits with status 1, leaving data/eclipses.json as it was, when the
    validation fails.
    """
    print("=" * 60)
    print("Your First Light -- Eclipse Catalogue Updater")
    print("=" * 60)
    print()

    print("[1/2] Fetching solar eclipses...")
    solar = fetch_eclipse_dates(_SOLAR_URLS, "Solar")

    print()
    print("[2/2] Fetching lunar eclipses...")
    lunar = fetch_eclipse_dates(_LUNAR_URLS, "Lunar")

    errors = validate(solar, lunar)
    if errors:
        print(f"\nERROR: {len(errors)} validation failure(s):")
        for e in errors:
            print(f"  - {e}")
        print("\nData NOT written. Fix the issues above before retrying.")
        sys.exit(1)

    print("\nValidation passed")
    changed = write_eclipses(solar, lunar)

    print("\nSummary:")
    print(f"  Solar eclipses: {len(solar)}")
    print(f"  Lunar eclipses: {len(lunar)}")
    print(f"  Total: {len(solar) + len(lunar)}")

    print()
    if changed:
        print("Done! Review the diff, then commit data/eclipses.json")
        print("(the scheduled workflow does this via a pull request).")
    else:
        print("Done! Catalogue already up to date.")


if __name__ == "__main__":
    main()
