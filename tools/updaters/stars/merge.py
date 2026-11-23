"""One entry per physical star, from the catalogues and curated tables.

Cross-catalogue matching has three tiers.

Tier 1 (same position): entries from different catalogues within
COINCIDENT_SEP_ARCSEC of each other are the same star however much
their distances disagree. With some 55,000 stars on the whole sky,
chance alignments this close are expected well under once, while
Gliese photometric parallaxes and faint HIPPARCOS parallaxes routinely
disagree with Gaia by 10 to 80 per cent, so a distance test at this
range would create duplicates rather than prevent them. When either
position comes from the Gliese catalogue the radius is
GLIESE_COINCIDENT_SEP_ARCSEC instead: its positions are quantised to a
second of time and carry fifty years of proper motion known to a few
tenths of an arcsecond a year for faint stars, so the same star often
lands 15 to 30 arcsec from its Gaia entry. Chance alignments within
30 arcsec are still expected under once.

Tier 2 (wide window): between COINCIDENT_SEP_ARCSEC and
MERGE_MAX_SEP_DEG the distances must also agree within a tolerance that
grows with distance, because a window this wide holds unrelated stars.
The window exists only to absorb the Gliese catalogue's coarse
positions (a second of time in RA, 0.1 arcmin in Dec, fifty years of
motion from a position angle quoted to 0.1 degrees). It never applies
between two positions from HIPPARCOS or Gaia: at a common epoch those
agree to well under an arcsecond for the same star, so two of them
further apart than tier 1 are two stars, typically a wide companion at
the same distance (Epsilon Indi A and its brown dwarf pair, 400 arcsec
apart).

Tier 3 (like brightness): within TWIN_MAX_SEP_ARCSEC, two entries whose
V magnitudes agree within TWIN_MAX_MAG_DIFF are the same star however
much their distances disagree. It catches the Gliese rows whose
parallax, often a photometric estimate, is too far off for tier 2,
which would leave the star listed twice: once at the Gliese distance
and once at the distance Gaia or HIPPARCOS measured. Like tier 2, it
never applies between two positions from HIPPARCOS or Gaia.

No tier joins two entries more than MERGE_MAX_MAG_DIFF apart in
magnitude: they are two stars, such as a bright star with no Gaia row
of its own and a faint star beside it.

Before any tier, a HIPPARCOS star that Gaia DR3 has matched joins only
that Gaia row (see hipparcos.fetch_hipparcos), and such pairs join
first.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict

from tools.updaters.stars.astrometry import ARCSEC_PER_DEG, angular_sep_deg
from tools.updaters.stars.curated import KNOWN_STAR_OVERRIDES
from tools.updaters.stars.entry import (
    MAGNITUDE_DECIMALS,
    Star,
    is_catalogue_id,
    sources_of,
)
from tools.updaters.stars.photometry import MISSING_MAGNITUDE

COINCIDENT_SEP_ARCSEC = 15.0
GLIESE_COINCIDENT_SEP_ARCSEC = 30.0
MERGE_MAX_SEP_DEG = 0.15  # 540 arcsec

# Tier 2 distance agreement grows with distance, as parallax error and
# so the disagreement between catalogues does: several light-years is
# normal beyond about 20 ly, and a fixed 1 ly tolerance lets thousands
# of duplicated stars through.
MERGE_DIST_TOL_FRACTION = 0.10
MERGE_DIST_TOL_FLOOR_LY = 1.0

# Tier 3. The Gliese catalogue, many of whose parallaxes are
# photometric estimates, puts some sixty stars at 0.26 to 1.9 times
# the distance Gaia or HIPPARCOS measured and up to 168 arcsec from
# their place, so neither other tier joins the two rows. Their V
# magnitudes agree within 0.2 mag, and their proper motions and
# SIMBAD's identifiers show each pair is one star or, four times, the
# two components of one binary. Rows this alike and this close that
# are not one star are rare (the components of an equal binary, one
# chance pair), and in most such pairs one row has a nearer match,
# which the merge takes first. Not in all: where both components of
# an equal binary lie this far from their Gliese places, the nearest
# pair can be the wrong one: NN 3999 A and NN 4000 B each take the
# other's Gaia row, 0.4 light-years from their own.
TWIN_MAX_MAG_DIFF = 0.2
TWIN_MAX_SEP_ARCSEC = 180.0

# Two catalogues' magnitudes of one star, V or G, differ by well under
# this, a hundredfold in flux: even the reddest dwarfs the G to V
# relation covers have a G only 3.6 mag brighter than their V.
MERGE_MAX_MAG_DIFF = 5.0
# Within the Gliese catalogue's position errors, the nearer of two
# close rows is often the wrong star: NN 4288 B lies nearer the Gaia
# row of NN 4288 A than A does. Magnitude tells them apart, so among
# pairs within GLIESE_COINCIDENT_SEP_ARCSEC that involve a Gliese
# position, those whose V magnitudes agree within LIKE_MAG_DIFF join
# first.
LIKE_MAG_DIFF = 0.5

# Two entries with the same common name are one star unless the
# catalogues put them this far apart.
SAME_NAME_MAX_SEP_DEG = 5.0

# Relative reliability of each source's parallaxes. A merged entry takes
# its distance, and the position that comes with it, from the most
# reliable catalogue it draws on.
SOURCE_QUALITY = {"gliese": 1, "hipparcos": 2, "gaia": 3}


def distance_tolerance_ly(distance_ly: float) -> float:
    """How far apart tier 2 lets two distances of one star be."""
    return max(MERGE_DIST_TOL_FLOOR_LY, MERGE_DIST_TOL_FRACTION * distance_ly)


def has_precise_position(star: Star) -> bool:
    """Whether an entry's position is HIPPARCOS or Gaia astrometry.

    Gliese positions and curated entries are not precise.
    """
    return star.get("_pos_source") in ("hipparcos", "gaia")


def same_star(a: Star, b: Star) -> bool:
    """Whether two entries are likely one physical star.

    The rules, in order:

    - Two entries with HIP numbers match only when the numbers do, and
      two with Gaia DR3 source IDs only when the IDs do.
    - Entries whose sources overlap never match: two rows of one
      catalogue are two objects, such as a resolved binary.
    - Two common names match when they are equal and close on the
      sky; different common names never match.
    - Otherwise at least one is a catalogue designation, and the
      tiers in the module docstring decide, after the magnitude gate.
    """
    hip_a: int | None = a.get("_hip_id")
    hip_b: int | None = b.get("_hip_id")
    if hip_a and hip_b:
        return hip_a == hip_b
    gaia_a: str | None = a.get("_gaia_id")
    gaia_b: str | None = b.get("_gaia_id")
    if gaia_a and gaia_b:
        return gaia_a == gaia_b

    if sources_of(a) & sources_of(b):
        return False

    sep = angular_sep_deg(
        a.get("ra_deg"),
        a.get("dec_deg"),
        b.get("ra_deg"),
        b.get("dec_deg"),
    )

    a_common = not is_catalogue_id(a["name"])
    b_common = not is_catalogue_id(b["name"])
    if a_common and b_common:
        if a["name"].lower() == b["name"].lower():
            return sep < SAME_NAME_MAX_SEP_DEG
        return False

    if not magnitudes_agree(a, b):
        return False

    both_precise = has_precise_position(a) and has_precise_position(b)
    coincident_arcsec = (
        COINCIDENT_SEP_ARCSEC if both_precise else GLIESE_COINCIDENT_SEP_ARCSEC
    )
    if sep < coincident_arcsec / ARCSEC_PER_DEG:
        return True

    if both_precise:
        return False

    # Magnitudes are kept to MAGNITUDE_DECIMALS, and the difference of
    # two such numbers is not exact in binary: 12.89 - 12.69 comes out
    # a hair over 0.2 and 12.69 - 12.49 a hair under. Rounding it makes
    # a pair exactly at the limit join whichever row is the brighter.
    if (
        a.get("magnitude_band") == b.get("magnitude_band") == "V"
        and MISSING_MAGNITUDE
        not in (a["apparent_magnitude"], b["apparent_magnitude"])
        and round(
            abs(a["apparent_magnitude"] - b["apparent_magnitude"]),
            MAGNITUDE_DECIMALS,
        )
        <= TWIN_MAX_MAG_DIFF
        and sep < TWIN_MAX_SEP_ARCSEC / ARCSEC_PER_DEG
    ):
        return True

    dist_diff = abs(a["distance_ly"] - b["distance_ly"])
    tol = distance_tolerance_ly(min(a["distance_ly"], b["distance_ly"]))
    return dist_diff < tol and sep < MERGE_MAX_SEP_DEG


def magnitudes_agree(a: Star, b: Star) -> bool:
    """Whether two entries are close enough in magnitude to be one star.

    They are within ``MERGE_MAX_MAG_DIFF``. An entry with no magnitude
    agrees with any.
    """
    mag_a: float = a["apparent_magnitude"]
    mag_b: float = b["apparent_magnitude"]
    if MISSING_MAGNITUDE in (mag_a, mag_b):
        return True
    return abs(mag_a - mag_b) <= MERGE_MAX_MAG_DIFF


def absorb(existing: Star, star: Star) -> None:
    """Folds a duplicate entry into the merged entry it matches.

    Keeps the common name over a designation, a V-band magnitude over a
    G-band one and any magnitude over none, the higher exoplanet count
    and any HIP number, Gaia source ID or Gliese system. Each
    catalogue's spectral type is kept, in merge order, in
    ``_spectral_types``, for ``photometry.fix_spectral_types`` to choose
    from once the distance is final. The distance and position come
    from the most reliable catalogue (Gaia, then HIPPARCOS, then
    Gliese): the best parallax comes with the best astrometry, and a
    merged entry must not keep a Gliese position quantised to a second
    of time.
    """
    if is_catalogue_id(existing["name"]) and not is_catalogue_id(star["name"]):
        existing["name"] = star["name"]
    existing["_spectral_types"] = [
        *existing.get("_spectral_types", [existing["spectral_type"]]),
        star["spectral_type"],
    ]
    if star["known_exoplanets"] > existing["known_exoplanets"]:
        existing["known_exoplanets"] = star["known_exoplanets"]
    if not existing.get("_hip_id") and star.get("_hip_id"):
        existing["_hip_id"] = star["_hip_id"]
    if not existing.get("_gaia_id") and star.get("_gaia_id"):
        existing["_gaia_id"] = star["_gaia_id"]
    if not existing.get("_gliese_system") and star.get("_gliese_system"):
        existing["_gliese_system"] = star["_gliese_system"]
    if existing.get("ra_deg") is None and star.get("ra_deg") is not None:
        existing["ra_deg"] = star["ra_deg"]
        existing["dec_deg"] = star["dec_deg"]
        existing["_pos_source"] = star.get("_pos_source")
    if star["apparent_magnitude"] != MISSING_MAGNITUDE and (
        existing["apparent_magnitude"] == MISSING_MAGNITUDE
        or (
            existing.get("magnitude_band") == "G"
            and star.get("magnitude_band") == "V"
        )
    ):
        existing["apparent_magnitude"] = star["apparent_magnitude"]
        existing["magnitude_band"] = star["magnitude_band"]

    if _distance_quality(star) > _distance_quality(existing):
        existing["distance_ly"] = star["distance_ly"]
        existing["_dist_source"] = _distance_source(star)
        if star.get("ra_deg") is not None:
            existing["ra_deg"] = star["ra_deg"]
            existing["dec_deg"] = star["dec_deg"]
            existing["_pos_source"] = star.get("_pos_source")

    existing["_merged_sources"] = sources_of(existing) | sources_of(star)


def _distance_source(star: Star) -> str | None:
    return star.get("_dist_source") or star.get("_source")


def _distance_quality(star: Star) -> int:
    """``SOURCE_QUALITY`` of an entry's distance; 0 for curated ones."""
    source = _distance_source(star)
    return SOURCE_QUALITY.get(source, 0) if source else 0


def merge_catalogues(*catalogues: list[Star]) -> list[Star]:
    """Merges star lists into one entry per star.

    Each catalogue in turn is matched against the entries merged so
    far, closest pair first across every candidate pair, and each
    merged entry absorbs at most one row of it. A row therefore joins
    the entry it is nearest rather than whichever entry it reaches
    first, so a bright star's own Gaia row is not left over as a second
    entry because a faint companion's row came earlier, and binary
    components pair with the right counterparts. Pairs that share a
    HIP number or Gaia source ID go first, and within the Gliese
    catalogue's position errors so do pairs of like magnitude
    (``LIKE_MAG_DIFF``). Rows are taken in catalogue ID order, so the
    result does not depend on the order an upstream service returned
    them in. Earlier catalogues win names and magnitudes.

    Returns:
        The merged entries. The given entries are left unchanged.
    """
    merged: list[Star] = []
    for catalogue in catalogues:
        rows = sorted(catalogue, key=_row_order)
        absorbed: set[int] = set()
        matched: set[int] = set()
        for _order, i, j in sorted(_candidate_pairs(merged, rows)):
            if i in absorbed or j in matched:
                continue
            absorb(merged[i], rows[j])
            absorbed.add(i)
            matched.add(j)
        merged.extend(
            dict(row) for j, row in enumerate(rows) if j not in matched
        )
    return merged


def _row_order(star: Star) -> tuple[str, str, float, float]:
    # The name orders entries that have no catalogue ID. The distance
    # and magnitude order two rows a catalogue gives one designation,
    # so that the one dedup_by_name keeps is not left to upstream order.
    return (
        star.get("_catalogue_id", ""),
        star["name"],
        star["distance_ly"],
        star["apparent_magnitude"],
    )


def _candidate_pairs(
    merged: list[Star], rows: list[Star]
) -> list[tuple[tuple[int, float], int, int]]:
    """Every pair of a merged entry and a row that may be one star.

    Returns:
        ``(order, merged_index, row_index)`` for each pair
        ``same_star`` accepts, where sorting by ``order``
        (``_pair_order``) puts the pairs to join first in front.
    """
    # A declination gap is a lower bound on the separation, so a window
    # in declination rules most entries out before any trigonometry.
    by_dec = sorted(
        (s["dec_deg"], i)
        for i, s in enumerate(merged)
        if s.get("dec_deg") is not None
    )
    decs = [dec for dec, _ in by_dec]
    unplaced = [i for i, s in enumerate(merged) if s.get("dec_deg") is None]
    pairs = []
    for j, row in enumerate(rows):
        dec = row.get("dec_deg")
        if dec is None:
            nearby: list[int] = list(range(len(merged)))
        else:
            lo = bisect_left(decs, dec - MERGE_MAX_SEP_DEG)
            hi = bisect_right(decs, dec + MERGE_MAX_SEP_DEG)
            nearby = [i for _, i in by_dec[lo:hi]] + unplaced
        for i in nearby:
            if same_star(merged[i], row):
                sep = angular_sep_deg(
                    merged[i].get("ra_deg"),
                    merged[i].get("dec_deg"),
                    row.get("ra_deg"),
                    dec,
                )
                pairs.append((_pair_order(merged[i], row, sep), i, j))
    return pairs


def _pair_order(entry: Star, row: Star, sep_deg: float) -> tuple[int, float]:
    """The sort key of a candidate pair: shared ID, like magnitudes, nearest.

    A pair that shares a HIP number or Gaia source ID comes first. Next
    come pairs where one position is not HIPPARCOS or Gaia astrometry,
    the two lie within ``GLIESE_COINCIDENT_SEP_ARCSEC`` and their V
    magnitudes agree within ``LIKE_MAG_DIFF``. Then the rest, each
    group nearest first.
    """
    if any(
        entry.get(key) and entry.get(key) == row.get(key)
        for key in ("_hip_id", "_gaia_id")
    ):
        return (0, sep_deg)
    like = (
        not (has_precise_position(entry) and has_precise_position(row))
        and sep_deg < GLIESE_COINCIDENT_SEP_ARCSEC / ARCSEC_PER_DEG
        and entry.get("magnitude_band") == row.get("magnitude_band") == "V"
        and MISSING_MAGNITUDE
        not in (entry["apparent_magnitude"], row["apparent_magnitude"])
        and round(
            abs(entry["apparent_magnitude"] - row["apparent_magnitude"]),
            MAGNITUDE_DECIMALS,
        )
        <= LIKE_MAG_DIFF
    )
    return (1 if like else 2, sep_deg)


def share_system_distances(stars: list[Star]) -> int:
    """Gives Gliese-only components their system's measured distance.

    The Gliese catalogue lists each component of a resolved multiple
    star, and the parallax of a faint one is often a photometric
    estimate. Where another component of the same system merged with a
    HIPPARCOS or Gaia row, that measured distance is the system's, and
    an entry drawn from the Gliese catalogue alone takes it: Gl 853 B
    would otherwise sit 39.6 light-years away to its primary's 45.9,
    and SIMBAD puts it at 44.7. With several such components, the
    nearest on the sky gives the distance. Works in place, after
    ``merge_catalogues``.

    Returns:
        The number of entries given a distance.
    """
    measured: defaultdict[str, list[Star]] = defaultdict(list)
    for s in stars:
        system = s.get("_gliese_system")
        if system and _distance_quality(s) > SOURCE_QUALITY["gliese"]:
            measured[system].append(s)
    changed = 0
    for s in stars:
        siblings = measured.get(s.get("_gliese_system") or "")
        if sources_of(s) != {"gliese"} or not siblings:
            continue
        sibling = min(
            siblings,
            key=lambda m: angular_sep_deg(
                s.get("ra_deg"),
                s.get("dec_deg"),
                m.get("ra_deg"),
                m.get("dec_deg"),
            ),
        )
        s["distance_ly"] = sibling["distance_ly"]
        s["_dist_source"] = _distance_source(sibling)
        changed += 1
    return changed


def remove_beyond(stars: list[Star], max_dist_ly: float) -> int:
    """Drops the entries further away than ``max_dist_ly``, in place.

    HIPPARCOS stars near the edge are fetched for their Gaia rows to
    place, and those that stay beyond it go here, with any Gliese
    component that took their distance.

    Returns:
        The number of entries dropped.
    """
    before = len(stars)
    stars[:] = [s for s in stars if s["distance_ly"] <= max_dist_ly]
    return before - len(stars)


def add_extra_stars(stars: list[Star], extras: list[Star]) -> tuple[int, int]:
    """Puts the curated extra stars in the catalogue, in place.

    An extra replaces the catalogue entry of the same name outright, as
    its values are hand-verified; one with a new name is appended.

    Returns:
        ``(added, replaced)`` counts.
    """
    added = 0
    replaced = 0
    index_by_name = {s["name"]: i for i, s in enumerate(stars)}
    for extra in extras:
        if extra["name"] in index_by_name:
            stars[index_by_name[extra["name"]]] = dict(extra)
            replaced += 1
        else:
            stars.append(dict(extra))
            added += 1
    return added, replaced


def dedup_by_coordinates(stars: list[Star], authoritative: list[Star]) -> int:
    """Removes designation-named entries that duplicate curated stars.

    After the extra stars go in, Gaia or Gliese entries for the same
    stars may remain under their designations. These are found with
    ``same_star``; curated entries carry no position source, so the
    wide distance-checked window applies to them and still catches a
    duplicate when the curated position is a few arcseconds off.

    Returns:
        The number of entries removed.
    """
    to_remove: list[int] = []
    auth_names = {s["name"] for s in authoritative}
    for i, s in enumerate(stars):
        if s["name"] in auth_names or not is_catalogue_id(s["name"]):
            continue
        for auth in authoritative:
            if auth.get("ra_deg") is None or s.get("ra_deg") is None:
                continue
            if same_star(s, auth):
                to_remove.append(i)
                break
    for i in sorted(set(to_remove), reverse=True):
        del stars[i]
    return len(to_remove)


def dedup_by_name(stars: list[Star]) -> int:
    """Removes repeated names in place.

    Of two entries with one name, the first stays unless only the
    second has a HIP number.

    Returns:
        The number of entries removed.
    """
    seen: dict[str, int] = {}
    to_remove: list[int] = []
    for i, s in enumerate(stars):
        if s["name"] not in seen:
            seen[s["name"]] = i
            continue
        prev_i = seen[s["name"]]
        if s.get("_hip_id") and not stars[prev_i].get("_hip_id"):
            to_remove.append(prev_i)
            seen[s["name"]] = i
        else:
            to_remove.append(i)
    for i in sorted(to_remove, reverse=True):
        del stars[i]
    return len(to_remove)


def apply_overrides(stars: list[Star]) -> int:
    """Overwrites entries named in ``KNOWN_STAR_OVERRIDES``, in place.

    Each overridden entry keeps the position the catalogues gave it as
    ``_catalogue_ra`` and ``_catalogue_dec``, so the validator can tell
    whether the override landed on the star it names.

    Returns:
        The number of entries overridden.
    """
    fixed = 0
    for s in stars:
        if s["name"] not in KNOWN_STAR_OVERRIDES:
            continue
        s["_catalogue_ra"] = s.get("ra_deg")
        s["_catalogue_dec"] = s.get("dec_deg")
        s.update(KNOWN_STAR_OVERRIDES[s["name"]])
        # Override magnitudes are SIMBAD V magnitudes.
        s["magnitude_band"] = "V"
        fixed += 1
    return fixed
