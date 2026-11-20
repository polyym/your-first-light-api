"""Checks that fail the run rather than write a wrong catalogue.

Each check returns a list of error messages; an empty list means it
passed.
"""

from tools.updaters.stars.astrometry import ARCSEC_PER_DEG, angular_sep_deg
from tools.updaters.stars.curated import (
    KNOWN_STAR_OVERRIDES,
    REFERENCE_POSITIONS,
)
from tools.updaters.stars.entry import Star, is_catalogue_id, sources_of
from tools.updaters.stars.merge import magnitudes_agree
from tools.updaters.stars.photometry import (
    absolute_magnitude,
    contradicts_magnitude,
)

# The catalogue covers anyone up to about 160 years old.
MAX_RADIUS_LY = 160

# The fewest entries (name keys for the Exoplanet Archive) each fetch
# may give, well below what each source gives (HIPPARCOS 6,500, Gliese
# 3,100 and Gaia 41,800 entries, Exoplanet Archive 10,300 keys). A
# fetch below its floor failed or silently degraded, and a catalogue
# built from the rest would look plausible while missing thousands of
# stars.
MIN_FETCH_COUNTS = {
    "hipparcos": 3_000,
    "gliese": 1_500,
    "gaia": 20_000,
    "exoplanet_archive": 1_000,
}

# How far from its REFERENCE_POSITIONS entry a fetch may put a
# reference star; this covers the Gliese catalogue's coarse positions
# (a second of time in RA, 0.1 arcmin in Dec).
REFERENCE_MAX_SEP_ARCSEC = 20.0

# How far an override's position may be from where the catalogues put
# the entry it lands on.
OVERRIDE_MAX_SEP_ARCSEC = 60.0

# Entries closer than DUPLICATE_SEP_ARCSEC whose distances disagree by
# more than max(FLOOR, FRACTION * distance) are one star listed twice.
# Components of one system agree in distance to within a few per cent.
DUPLICATE_SEP_ARCSEC = 15.0
DUPLICATE_DIST_TOL_FRACTION = 0.05
DUPLICATE_DIST_TOL_FLOOR_LY = 0.5

# Apparent magnitudes outside this open range are not real values.
BRIGHTEST_MAGNITUDE = -2
FAINTEST_MAGNITUDE = 30


def check_fetch_counts(counts: dict[str, int]) -> list[str]:
    """Flags upstream fetches that returned too little.

    Args:
        counts: Rows or keys returned, by ``MIN_FETCH_COUNTS`` key.
    """
    errors = []
    for label, count in counts.items():
        floor = MIN_FETCH_COUNTS[label]
        if count < floor:
            errors.append(
                f"FETCH: {label} returned {count} rows "
                f"(expected >= {floor}); refusing to build "
                f"a degraded catalogue"
            )
    return errors


def check_reference_positions(stars: list[Star], source: str) -> list[str]:
    """Flags a fetch that misplaces or misses a reference star.

    Args:
        stars: The entries one fetcher returned.
        source: The ``REFERENCE_POSITIONS`` key of that fetcher.
    """
    by_id = {s.get("_catalogue_id"): s for s in stars}
    errors = []
    for cid, (ra, dec) in REFERENCE_POSITIONS[source].items():
        star = by_id.get(cid)
        if star is None:
            errors.append(
                f"REFERENCE: {source} did not return {cid}; "
                f"refusing to build a catalogue from a fetch "
                f"missing a well-known nearby star"
            )
            continue
        sep_arcsec = (
            angular_sep_deg(star.get("ra_deg"), star.get("dec_deg"), ra, dec)
            * ARCSEC_PER_DEG
        )
        if sep_arcsec > REFERENCE_MAX_SEP_ARCSEC:
            errors.append(
                f"REFERENCE: {source} places {cid} "
                f"{sep_arcsec:.0f} arcsec from its J2000 position "
                f"(limit {REFERENCE_MAX_SEP_ARCSEC:.0f}); the "
                f"fetch is probably at the wrong epoch"
            )
    return errors


def find_positional_duplicates(
    stars: list[Star],
    max_sep_arcsec: float = DUPLICATE_SEP_ARCSEC,
) -> list[tuple[int, int, float]]:
    """Finds pairs of entries that look like one star listed twice.

    A pair is suspect when the positions nearly coincide but the
    distances disagree by more than a few per cent, the mark of one star
    coming in from catalogues whose parallaxes disagree. Exempt: pairs
    that agree in distance (components of one system), pairs sharing a
    source catalogue (a pair that catalogue resolved), pairs where both
    carry common names (curated system components), and pairs too far
    apart in magnitude to be one star (``merge.magnitudes_agree``).

    Returns:
        ``(index_a, index_b, separation_deg)`` for each pair.
    """
    max_sep_deg = max_sep_arcsec / ARCSEC_PER_DEG
    order = sorted(
        (i for i, s in enumerate(stars) if s.get("ra_deg") is not None),
        key=lambda i: stars[i]["dec_deg"],
    )
    pairs: list[tuple[int, int, float]] = []
    for pos, i in enumerate(order):
        for j in order[pos + 1 :]:
            # Sorted by declination: once the gap passes the limit, no
            # later entry can be close.
            if stars[j]["dec_deg"] - stars[i]["dec_deg"] > max_sep_deg:
                break
            a, b = stars[i], stars[j]
            if not is_catalogue_id(a["name"]) and not is_catalogue_id(
                b["name"]
            ):
                continue
            if sources_of(a) & sources_of(b) or not magnitudes_agree(a, b):
                continue
            sep = angular_sep_deg(
                a["ra_deg"], a["dec_deg"], b["ra_deg"], b["dec_deg"]
            )
            if sep >= max_sep_deg:
                continue
            d_a = a["distance_ly"]
            d_b = b["distance_ly"]
            tol = max(
                DUPLICATE_DIST_TOL_FLOOR_LY,
                DUPLICATE_DIST_TOL_FRACTION * min(d_a, d_b),
            )
            if abs(d_a - d_b) > tol:
                pairs.append((i, j, sep))
    return pairs


def validate_catalogue(stars: list[Star]) -> list[str]:
    """Checks the finished catalogue before it is written.

    Every problem found here should already have been fixed by an
    earlier step, so any error means the pipeline has a fault.
    """
    errors = []

    for i, j, sep in find_positional_duplicates(stars):
        errors.append(
            f"POSITIONAL_DUP: '{stars[i]['name']}' "
            f"({stars[i]['distance_ly']} ly) and "
            f"'{stars[j]['name']}' "
            f"({stars[j]['distance_ly']} ly) are "
            f"{sep * ARCSEC_PER_DEG:.1f} arcsec apart"
        )

    seen_names: dict[str, int] = {}
    for i, s in enumerate(stars):
        if s["name"] in seen_names:
            errors.append(
                f"DUPLICATE: '{s['name']}' at indices "
                f"{seen_names[s['name']]} and {i}"
            )
        seen_names[s["name"]] = i

    for name in KNOWN_STAR_OVERRIDES:
        if name not in seen_names:
            errors.append(f"MISSING: '{name}' not in catalogue")

    # A large gap between an override and where the catalogues put its
    # entry means a HIP or Gliese name mapping points at another star,
    # which the override has then silently overwritten.
    for s in stars:
        if s["name"] not in KNOWN_STAR_OVERRIDES:
            continue
        cat_ra = s.get("_catalogue_ra")
        cat_dec = s.get("_catalogue_dec")
        if cat_ra is None or cat_dec is None:
            continue
        ov = KNOWN_STAR_OVERRIDES[s["name"]]
        sep_arcsec = (
            angular_sep_deg(cat_ra, cat_dec, ov["ra_deg"], ov["dec_deg"])
            * ARCSEC_PER_DEG
        )
        if sep_arcsec > OVERRIDE_MAX_SEP_ARCSEC:
            errors.append(
                f"OVERRIDE_MISMATCH: '{s['name']}' override "
                f"landed on a catalogue entry {sep_arcsec:.0f} "
                f"arcsec away (limit "
                f"{OVERRIDE_MAX_SEP_ARCSEC:.0f}); a name "
                f"mapping points at the wrong star"
            )

    for s in stars:
        errors.extend(_range_errors(s))
        errors.extend(_spectral_type_errors(s))

    return errors


def _spectral_type_errors(s: Star) -> list[str]:
    """Flags a type its star's absolute magnitude rules out.

    ``photometry.fix_spectral_types`` replaces or clears such types for
    catalogue entries, so one here comes from a curated table or a
    fault in that step.
    """
    sp = s["spectral_type"]
    # _range_errors reports a distance that gives no absolute magnitude.
    if not sp or s["distance_ly"] <= 0:
        return []
    abs_v = absolute_magnitude(s["apparent_magnitude"], s["distance_ly"])
    if not contradicts_magnitude(sp, abs_v):
        return []
    return [
        f"SPECTRAL_TYPE: '{s['name']}' has type '{sp}' at absolute "
        f"magnitude {abs_v:.2f} ({s['apparent_magnitude']} at "
        f"{s['distance_ly']} ly), which that type rules out"
    ]


def _range_errors(s: Star) -> list[str]:
    errors = []
    d = s["distance_ly"]
    if not (0 < d <= MAX_RADIUS_LY):
        errors.append(
            f"RANGE: '{s['name']}' distance {d} outside (0, {MAX_RADIUS_LY}]"
        )
    mag = s["apparent_magnitude"]
    if not (BRIGHTEST_MAGNITUDE < mag < FAINTEST_MAGNITUDE):
        errors.append(
            f"RANGE: '{s['name']}' magnitude {mag} outside "
            f"({BRIGHTEST_MAGNITUDE}, {FAINTEST_MAGNITUDE})"
        )
    ra = s.get("ra_deg")
    if ra is not None and not (0 <= ra < 360):
        errors.append(f"RANGE: '{s['name']}' RA {ra} outside [0, 360)")
    dec = s.get("dec_deg")
    if dec is not None and not (-90 <= dec <= 90):
        errors.append(f"RANGE: '{s['name']}' Dec {dec} outside [-90, 90]")
    return errors
