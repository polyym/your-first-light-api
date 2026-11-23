"""The HIPPARCOS fetch: archive rows to entries."""

from typing import Any

import pytest
from astropy.table import MaskedColumn, Table

from tools.updaters.retry import FETCH_ATTEMPTS
from tools.updaters.stars.astrometry import min_parallax_mas
from tools.updaters.stars.hipparcos import archive_queries, fetch_hipparcos
from tools.updaters.stars.validate import MAX_RADIUS_LY

_COLUMNS = (
    "hip",
    "ra",
    "dec",
    "pm_ra",
    "pm_de",
    "plx",
    "e_plx",
    "vmag",
    "sptype",
    "source_id",
    "parallax",
    "parallax_error",
    "ruwe",
    "phot_g_mean_mag",
    "bp_rp",
)

# Archive rows as the ESA Gaia archive gives them: the 2007 reduction's
# astrometry, the 1997 catalogue's V and type, and Gaia DR3's match.
BARNARDS_STAR = (
    87937,
    269.45402262789094,
    4.668287809128218,
    -798.58,
    10328.12,
    548.31,
    1.51,
    9.54,
    "sdM4",
    4472832130942575872,
    546.975939730948,
    0.04011635482311249,
    1.084850549697876,
    8.193974494934082,
    2.8336968421936035,
)
# Gaia's match is a source of G 20.95 with no parallax.
ALPHA_CENTAURI_B = (
    71681,
    219.91412459936643,
    -60.83948046402479,
    -3614.39,
    802.98,
    796.92,
    25.9,
    1.35,
    "K1V",
    5877748442128924544,
    None,
    None,
    None,
    20.9486141204834,
    0.6318454742431641,
)
# 160.4 ly by HIPPARCOS. Gaia's match is a G 7.82 neighbour with no
# parallax; the star's own Gaia row, 156.3 ly away, is another source.
BETA_LEPORIS = (
    25606,
    82.06135954367498,
    -20.75923200083838,
    -5.02,
    -86.01,
    20.34,
    0.18,
    2.81,
    "G5II",
    2968097043227107840,
    None,
    None,
    None,
    7.821054458618164,
    0.5291957855224609,
)
# A V 4.5 giant: 20.47 +- 0.21 mas by HIPPARCOS, inside the cut, and
# 20.08 +- 0.11 by Gaia, outside it.
HIP_104459 = (
    104459,
    317.39830365932573,
    -11.371654773631494,
    94.12,
    -14.62,
    20.47,
    0.21,
    4.5,
    "G8III",
    6895103083539482496,
    20.084233986479735,
    0.11367826163768768,
    0.9254082441329956,
    4.251079559326172,
    1.1062934398651123,
)


def _unmatched(*astrometry: float) -> tuple[Any, ...]:
    """A row of V 11.0 and no type, which Gaia DR3 has not matched."""
    return (*astrometry, 11.0, "", None, None, None, None, None, None)


# Gienah, which Gaia DR3 has not matched.
GIENAH = (
    59803,
    183.95194934889173,
    -17.54198358562747,
    -158.61,
    21.86,
    21.23,
    0.2,
    2.58,
    "B8III",
    None,
    None,
    None,
    None,
    None,
    None,
)
# The eight entries SPURIOUS_HIP_IDS leaves out. HIP 21000 has a Gaia
# match, at 662 ly.
SPURIOUS = [
    (
        21000,
        67.552166,
        5.298527,
        97.46,
        119.01,
        93.67,
        7.62,
        9.83,
        "F8+...",
        3285409673726608768,
        4.926266717890942,
        0.0155634,
        0.92993,
        10.312016487121582,
        0.8202075958251953,
    ),
    _unmatched(82724, 253.632249, -62.400219, 322.48, 221.6, 270.53, 43.44),
    _unmatched(82725, 253.633962, -62.403732, 280.74, 189.74, 241.17, 33.78),
    _unmatched(85605, 262.40079, 24.653227, 86.61, 286.28, 146.84, 29.81),
    _unmatched(98681, 300.649406, -50.04938, 415.22, -293.0, 64.26, 22.65),
    _unmatched(114110, 346.662031, -14.872404, 97.84, 56.37, 208.16, 34.01),
    _unmatched(114176, 346.831371, -32.268191, -257.87, -5.0, 110.72, 45.94),
    _unmatched(10529, 33.91874, 67.677813, 518.48, -311.93, 47.8, 5.03),
]


def _table(*rows: tuple[Any, ...]) -> Table:
    """Archive rows, with a missing value masked as the archive's NULL."""
    columns = list(zip(*rows, strict=True))
    return Table(
        {
            name: MaskedColumn(
                [0 if v is None else v for v in values],
                mask=[v is None for v in values],
            )
            for name, values in zip(_COLUMNS, columns, strict=True)
        }
    )


def _row(base: tuple[Any, ...], **changes: Any) -> tuple[Any, ...]:
    values = dict(zip(_COLUMNS, base, strict=True)) | changes
    return tuple(values[name] for name in _COLUMNS)


def _fetch(archive: Any, *rows: tuple[Any, ...]) -> dict[int, dict[str, Any]]:
    archive.answers = [_table(*rows)]
    return {s["_hip_id"]: s for s in fetch_hipparcos(MAX_RADIUS_LY)}


def test_queries_take_every_star_that_may_be_inside_160_ly():
    """Three standard errors of a 2007 parallax, or Gaia's parallax.

    The joins are pinned too: an inner join to the match table in the
    first query would lose some 1,900 stars Gaia does not match, and
    every check would still pass.
    """
    columns = (
        "SELECT n.hip, n.ra, n.dec, n.pm_ra, n.pm_de, n.plx, n.e_plx, "
        "h.vmag, h.sptype, b.source_id, g.parallax, g.parallax_error, "
        "g.ruwe, g.phot_g_mean_mag, g.bp_rp "
    )
    by_hipparcos = (
        "FROM public.hipparcos_newreduction AS n "
        "LEFT OUTER JOIN public.hipparcos AS h ON h.hip = n.hip "
        "LEFT OUTER JOIN gaiadr3.hipparcos2_best_neighbour AS b "
        "ON b.original_ext_source_id = n.hip "
        "LEFT OUTER JOIN gaiadr3.gaia_source AS g "
        "ON g.source_id = b.source_id "
        "WHERE n.plx + 3 * n.e_plx > 20.38475"
    )
    by_gaia = (
        "FROM gaiadr3.gaia_source AS g "
        "JOIN gaiadr3.hipparcos2_best_neighbour AS b "
        "ON b.source_id = g.source_id "
        "JOIN public.hipparcos_newreduction AS n "
        "ON n.hip = b.original_ext_source_id "
        "LEFT OUTER JOIN public.hipparcos AS h ON h.hip = n.hip "
        "WHERE g.parallax > 20.38475"
    )
    assert archive_queries(min_parallax_mas(MAX_RADIUS_LY)) == [
        (f"{columns}{rows} ORDER BY n.hip", f"SELECT COUNT(*) {rows}")
        for rows in (by_hipparcos, by_gaia)
    ]


def test_answers_are_united_once_each_in_hip_order(archive, retry_waits):
    """A star in both answers, here HIP 104459, is listed once."""
    archive.answers = [_table(HIP_104459, GIENAH), _table(HIP_104459)]
    stars = fetch_hipparcos(MAX_RADIUS_LY)
    assert [s["_hip_id"] for s in stars] == [59803, 104459]


def test_star_only_gaia_puts_inside_is_kept(archive, retry_waits):
    """A star whose 2007 parallax is beyond reach: 18.0 +- 0.21 mas."""
    inside_by_gaia = _row(BARNARDS_STAR, plx=18.0, e_plx=0.21)
    archive.answers = [_table(GIENAH), _table(inside_by_gaia)]
    stars = {s["_hip_id"]: s for s in fetch_hipparcos(MAX_RADIUS_LY)}
    assert stars[87937]["distance_ly"] == pytest.approx(5.9629, abs=1e-4)


def test_one_failed_answer_gives_no_stars(archive, retry_waits, capsys):
    archive.answers = [_table(GIENAH), ConnectionError("timed out")]
    assert fetch_hipparcos(MAX_RADIUS_LY) == []
    out = capsys.readouterr().out
    assert "HIPPARCOS (Gaia match) archive query failed: timed out" in out


def test_failed_first_query_stops_the_fetch(archive, retry_waits, capsys):
    archive.answers = [ConnectionError("timed out")]
    assert fetch_hipparcos(MAX_RADIUS_LY) == []
    assert len(archive.queries) == FETCH_ATTEMPTS
    out = capsys.readouterr().out
    assert "HIPPARCOS (2007 parallax) archive query failed: timed out" in out


def test_row_becomes_an_entry_at_its_gaia_match_s_distance(
    archive, retry_waits
):
    barnard = _fetch(archive, BARNARDS_STAR)[87937]
    assert barnard["name"] == "Barnard's Star"
    assert barnard["_gaia_id"] == "4472832130942575872"
    # Gaia's 546.98 mas, not the 2007 reduction's 548.31.
    assert barnard["distance_ly"] == pytest.approx(5.9629, abs=1e-4)
    assert barnard["spectral_type"] == "sdM4"
    # Its J2000 position, 10 arcsec a year from where HIPPARCOS saw it.
    assert barnard["ra_deg"] == pytest.approx(269.45208, abs=1e-4)
    assert barnard["dec_deg"] == pytest.approx(4.69336, abs=1e-4)


def test_row_with_no_gaia_match_keeps_its_2007_distance(archive, retry_waits):
    """Gienah, which Gaia DR3 does not match: 21.23 +- 0.20 mas."""
    stars = _fetch(archive, GIENAH)
    assert stars[59803]["distance_ly"] == pytest.approx(153.63, abs=0.01)
    assert stars[59803]["spectral_type"] == "B8III"
    assert "_gaia_id" not in stars[59803]


def test_star_gaia_puts_beyond_the_cut_is_kept_for_the_merge_to_drop(
    archive, retry_waits
):
    """HIP 104459: 159.3 ly by HIPPARCOS, 162.4 by Gaia.

    Leaving it out here would keep any Gliese row of it, unjoined, at
    the Gliese distance.
    """
    star = _fetch(archive, HIP_104459)[104459]
    assert star["distance_ly"] == pytest.approx(162.39, abs=0.01)
    assert star["_gaia_id"] == "6895103083539482496"


@pytest.mark.parametrize(
    "changes",
    [
        {"ruwe": 1.5, "parallax_error": 1.5},
        {"parallax_error": 4.5},
        {"parallax": None, "parallax_error": None},
    ],
    ids=["fails-the-ruwe-rule", "under-5-errors", "no-parallax"],
)
def test_match_with_an_unsound_parallax_is_no_match(
    archive, retry_waits, changes
):
    """HIP 104459 stays, at the 2007 distance."""
    stars = _fetch(archive, _row(HIP_104459, **changes))
    assert stars[104459]["distance_ly"] == pytest.approx(159.33, abs=0.01)
    assert "_gaia_id" not in stars[104459]


def test_match_of_another_brightness_is_no_match(archive, retry_waits):
    """Alpha Centauri B, V 1.35, against Gaia's G 20.95 source."""
    sound = {"parallax": 747.0, "parallax_error": 0.1, "ruwe": 1.0}
    stars = _fetch(archive, _row(ALPHA_CENTAURI_B, **sound))
    assert "_gaia_id" not in stars[71681]


@pytest.mark.parametrize(
    ("gmag", "matched"), [(10.14, True), (10.16, False)], ids=["1.99", "2.01"]
)
def test_match_must_be_within_2_magnitudes_of_v(
    archive, retry_waits, gmag, matched
):
    """Barnard's Star at BP-RP 2.83, where Gaia's G is 1.39 under V."""
    stars = _fetch(archive, _row(BARNARDS_STAR, phot_g_mean_mag=gmag))
    assert ("_gaia_id" in stars[87937]) is matched


@pytest.mark.parametrize("missing", ["vmag", "phot_g_mean_mag"])
def test_match_with_a_missing_magnitude_counts(archive, retry_waits, missing):
    stars = _fetch(archive, _row(BARNARDS_STAR, **{missing: None}))
    assert stars[87937]["_gaia_id"] == "4472832130942575872"


def test_star_just_beyond_the_cut_by_hipparcos_is_kept_for_the_merge(
    archive, retry_waits
):
    """Beta Leporis, at 160.4 ly, until its own Gaia row places it."""
    stars = _fetch(archive, BETA_LEPORIS)
    assert stars[25606]["distance_ly"] == pytest.approx(160.35, abs=0.01)
    assert "_gaia_id" not in stars[25606]


def test_spurious_entries_are_left_out(archive, retry_waits):
    """HIP 21000's Gaia match, at 662 ly, would keep it for the merge.

    Three others, with 2007 parallaxes under five standard errors, would
    leave without the list.
    """
    stars = _fetch(archive, *SPURIOUS, BARNARDS_STAR)
    assert list(stars) == [87937]


def test_weak_2007_parallax_with_no_match_is_left_out(archive, retry_waits):
    stars = _fetch(archive, _unmatched(1, 10.0, 10.0, 0.0, 0.0, 30.0, 7.0))
    assert stars == {}


@pytest.mark.filterwarnings("error")
def test_weak_2007_parallax_gives_way_to_the_gaia_match_quietly(
    archive, retry_waits
):
    """HIP 81594, -6.97 +- 6.69 mas, comes in through its Gaia match."""
    stars = _fetch(archive, _row(BARNARDS_STAR, plx=-6.97, e_plx=6.69))
    assert stars[87937]["distance_ly"] == pytest.approx(5.9629, abs=1e-4)
