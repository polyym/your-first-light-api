"""Confirmed planet counts from the NASA Exoplanet Archive."""

from collections import Counter, defaultdict

import numpy as np

from tools.updaters.retry import with_retries
from tools.updaters.stars.curated import EXOPLANET_NAME_ALIASES
from tools.updaters.stars.entry import Star

# Planetary Systems Composite Parameters: one row per confirmed planet.
ARCHIVE_TABLE = "pscomppars"
_ARCHIVE_COLUMNS = "hostname,hip_name,hd_name,gaia_dr3_id"


def fetch_exoplanet_counts() -> dict[str, int]:
    """Fetches the confirmed planet count of every host star.

    A host's planets are its own rows, not the archive's ``sy_pnum``,
    which counts the planets of every star in the system: 55 Cancri A
    has five planets and its companion two, and ``sy_pnum`` gives both
    seven.

    Returns:
        The planet count recorded under each name a host goes by (host
        name and HIP, HD and Gaia DR3 designations), or an empty dict
        after printing a warning when every attempt at the query
        failed. The fetch guard then fails the run. A HIP number
        without its component letter counts the planets of every host
        that shares it, since HIPPARCOS lists such a pair as one star.
        So does the Gaia DR3 source of such a pair when the archive
        gives one to only one of its hosts: Gaia did not resolve them
        either (HD 41004 A and B, half an arcsecond apart).
    """
    # astroquery is only in the catalogue dependency group; importing it
    # here lets the rest of the updater, and its tests, run without it.
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import (
        NasaExoplanetArchive,
    )

    print("[4/4] Querying NASA Exoplanet Archive...")
    try:
        table = with_retries(
            lambda: NasaExoplanetArchive.query_criteria(
                table=ARCHIVE_TABLE, select=_ARCHIVE_COLUMNS
            ),
            "Exoplanet Archive query",
        )
    except Exception as e:
        # Any failure means the same: no counts to build on.
        print(f"  WARNING: Exoplanet Archive query failed: {e}")
        return {}

    planets: Counter[str] = Counter()
    other_names: defaultdict[str, set[str]] = defaultdict(set)
    hosts_by_hip_number: defaultdict[str, set[str]] = defaultdict(set)
    gaia_sources: dict[str, str] = {}
    for row in table:
        hostname = _name_cell(row["hostname"])
        planets[hostname] += 1
        hip = _name_cell(row["hip_name"])
        if hip:
            hip_number = hip.replace("HIP", "").strip().split()[0]
            hosts_by_hip_number[f"HIP {hip_number}"].add(hostname)
        gaia = _name_cell(row["gaia_dr3_id"])
        if gaia:
            gaia_sources[hostname] = gaia
        other_names[hostname] |= {hip, _name_cell(row["hd_name"]), gaia}

    counts: dict[str, int] = {}
    for hostname, pnum in planets.items():
        for name in {hostname, *other_names[hostname]}:
            _keep_max(counts, name, pnum)
    for hip_key, hostnames in hosts_by_hip_number.items():
        pair_planets = sum(planets[h] for h in hostnames)
        _keep_max(counts, hip_key, pair_planets)
        sourced = [h for h in hostnames if h in gaia_sources]
        if len(hostnames) > 1 and len(sourced) == 1:
            _keep_max(counts, gaia_sources[sourced[0]], pair_planets)

    print(f"  Found exoplanet data for {len(counts)} keys")
    return counts


def _name_cell(value: object) -> str:
    return str(value).strip() if not np.ma.is_masked(value) else ""


def _keep_max(counts: dict[str, int], key: str, pnum: int) -> None:
    if key:
        counts[key] = max(counts.get(key, 0), pnum)


def match_exoplanets(stars: list[Star], exo_counts: dict[str, int]) -> int:
    """Sets each entry's planet count from the archive, in place.

    Looks each entry up in ``exo_counts``, from
    ``fetch_exoplanet_counts``, by its Gaia DR3 source, then its name,
    then its archive aliases, then its HIP number in both spellings the
    archive uses. The Gaia source comes first because it names one
    star, where a HIP number may stand for a pair, and because the
    archive calls most faint hosts by names no catalogue here uses
    (L 98-59, LHS 1140).

    Returns:
        The number of entries matched.
    """
    matched = 0
    for s in stars:
        keys_to_try = []
        if "_gaia_id" in s:
            keys_to_try.append(f"Gaia DR3 {s['_gaia_id']}")
        keys_to_try.append(s["name"])
        keys_to_try.extend(EXOPLANET_NAME_ALIASES.get(s["name"], []))
        if "_hip_id" in s:
            keys_to_try.append(f"HIP {s['_hip_id']}")
            keys_to_try.append(f"HIP{s['_hip_id']}")

        for key in keys_to_try:
            if key in exo_counts:
                s["known_exoplanets"] = exo_counts[key]
                matched += 1
                break
    return matched
