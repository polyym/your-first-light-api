"""Gaia DR3 from the ESA Gaia archive."""

import sys
import types

import pytest
from astropy.table import MaskedColumn, Table

from tools.updaters.retry import FETCH_ATTEMPTS
from tools.updaters.stars.astrometry import min_parallax_mas
from tools.updaters.stars.gaia import (
    archive_count_query,
    archive_query,
    fetch_gaia,
)
from tools.updaters.stars.validate import (
    MAX_RADIUS_LY,
    check_reference_positions,
)

# Archive rows: the three reference stars, a star with no BP-RP colour,
# one whose parallax is under five standard errors, Epsilon Indi Ba and
# Bb, whose orbit the single-star solution does not fit (RUWE 4.30) but
# whose parallax is 392 standard errors, and a faint row in the Cygnus
# plane whose solution fits no better (RUWE 3.61) and whose parallax is
# only 17 standard errors.
_ROWS = {
    "source_id": [
        4472832130942575872,
        4034171629042489088,
        4810594479418041856,
        272929645359298944,
        1833005562778915712,
        6412596012146801152,
        2031272798024664960,
    ],
    "ra": [
        269.448502525,
        178.267353208,
        77.959937350,
        70.861080677,
        301.222525834,
        331.076452597,
        295.993136131,
    ],
    "dec": [
        4.739420051,
        37.692826947,
        -45.043812699,
        53.305550308,
        22.510308892,
        -56.793812067,
        28.256388833,
    ],
    "pmra": [-801.551, 4002.655, 6491.223, 20.978, -7.457, 3981.977, 19.453],
    "pmdec": [
        10362.394,
        -5817.800,
        -5708.614,
        -154.372,
        -7.069,
        -2466.832,
        -8.135,
    ],
    "parallax": [546.976, 109.030, 254.199, 20.937, 20.467, 270.658, 58.410],
    "parallax_error": [0.0401, 0.0197, 0.0168, 0.1140, 4.2618, 0.6896, 3.393],
    "phot_g_mean_mag": [8.194, 6.199, 8.064, 16.770, 20.833, 18.031, 20.359],
    "bp_rp": [2.834, 1.002, 2.027, 0.0, 1.097, 5.082, 1.341],
    "ruwe": [1.085, 0.880, 1.170, 1.051, 1.307, 4.296, 3.61],
}
_NO_COLOUR = [False, False, False, True, False, False, False]
# The rows that become entries.
_KEPT = [0, 1, 2, 3, 5]


def _archive_table() -> Table:
    table = Table({name: MaskedColumn(v) for name, v in _ROWS.items()})
    table["bp_rp"].mask = _NO_COLOUR
    return table


class _Archive:
    """The queries sent, and the answers to give: a table or an error.

    A count query is answered with ``matching``, or by default with the
    length of the table just sent.
    """

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.count_queries: list[str] = []
        self.answers: list[Table | Exception] = []
        self.matching: int | None = None
        self._sent = 0

    def launch_job_async(self, adql: str) -> types.SimpleNamespace:
        if adql.startswith("SELECT COUNT(*)"):
            self.count_queries.append(adql)
            matching = self._sent if self.matching is None else self.matching
            counts = Table({"COUNT_ALL": [matching]})
            return types.SimpleNamespace(get_results=lambda: counts)
        self.queries.append(adql)
        queue = self.answers
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        self._sent = len(answer)
        return types.SimpleNamespace(get_results=lambda: answer)


@pytest.fixture
def archive(monkeypatch: pytest.MonkeyPatch) -> _Archive:
    """Stands astroquery's Gaia in for the ESA Gaia archive."""
    gaia = _Archive()
    module = types.ModuleType("astroquery.gaia")
    module.Gaia = gaia
    monkeypatch.setitem(
        sys.modules, "astroquery", types.ModuleType("astroquery")
    )
    monkeypatch.setitem(sys.modules, "astroquery.gaia", module)
    return gaia


def test_query_takes_every_star_inside_160_ly_in_a_fixed_order():
    """The cut is the parallax at 160 ly, not 20.4 mas (159.88 ly)."""
    assert archive_query(min_parallax_mas(MAX_RADIUS_LY)) == (
        "SELECT source_id, ra, dec, pmra, pmdec, parallax, parallax_error, "
        "phot_g_mean_mag, bp_rp, ruwe FROM gaiadr3.gaia_source "
        "WHERE parallax > 20.38475 ORDER BY source_id"
    )


def test_archive_rows_become_entries(archive, retry_waits):
    archive.answers = [_archive_table()]
    stars = fetch_gaia(MAX_RADIUS_LY)
    min_parallax = min_parallax_mas(MAX_RADIUS_LY)
    assert archive.queries == [archive_query(min_parallax)]
    assert archive.count_queries == [archive_count_query(min_parallax)]
    assert [s["_catalogue_id"] for s in stars] == [
        str(_ROWS["source_id"][i]) for i in _KEPT
    ]
    assert stars[0]["name"] == "Gaia DR3 4472832130942575872"
    assert stars[0]["_gaia_id"] == "4472832130942575872"
    assert stars[0]["distance_ly"] == pytest.approx(5.963, abs=1e-3)
    assert [s["magnitude_band"] for s in stars][:4] == ["V", "V", "V", "G"]
    assert stars[3]["apparent_magnitude"] == 16.77
    assert check_reference_positions(stars, "gaia") == []


def test_high_ruwe_row_with_a_strong_parallax_is_kept(archive, retry_waits):
    """Epsilon Indi Ba and Bb, at RUWE 4.30, are 12 ly away."""
    archive.answers = [_archive_table()]
    stars = {s["name"]: s for s in fetch_gaia(MAX_RADIUS_LY)}
    epsilon_indi_b = stars["Gaia DR3 6412596012146801152"]
    assert epsilon_indi_b["distance_ly"] == pytest.approx(12.05, abs=0.01)
    # A pair of brown dwarfs, at absolute G 20.19.
    assert epsilon_indi_b["spectral_type"] == "L (est)"


def test_high_ruwe_row_with_a_weak_parallax_is_left_out(archive, retry_waits):
    archive.answers = [_archive_table()]
    names = {s["name"] for s in fetch_gaia(MAX_RADIUS_LY)}
    assert "Gaia DR3 2031272798024664960" not in names


def test_row_with_no_ruwe_needs_a_strong_parallax(archive, retry_waits):
    """A missing RUWE counts as a poor fit, not as a good one."""
    table = _archive_table()
    # Barnard's Star, at 13,640 standard errors, and the Cygnus row.
    table["ruwe"].mask = [True, False, False, False, False, False, True]
    archive.answers = [table]
    names = {s["name"] for s in fetch_gaia(MAX_RADIUS_LY)}
    assert "Gaia DR3 4472832130942575872" in names
    assert "Gaia DR3 2031272798024664960" not in names


def test_row_with_no_parallax_error_is_left_out(archive, retry_waits):
    table = _archive_table()
    table["parallax_error"].mask = [True] + [False] * 6
    archive.answers = [table]
    names = {s["name"] for s in fetch_gaia(MAX_RADIUS_LY)}
    assert "Gaia DR3 4472832130942575872" not in names
    assert len(names) == len(_KEPT) - 1


def test_short_answer_is_retried(archive, retry_waits):
    archive.answers = [_archive_table()[:3], _archive_table()]
    archive.matching = len(_ROWS["source_id"])
    assert len(fetch_gaia(MAX_RADIUS_LY)) == len(_KEPT)
    assert len(archive.queries) == 2
    assert len(retry_waits) == 1


def test_answer_that_stays_short_gives_no_stars(archive, retry_waits, capsys):
    """The archive once cut its answer off at 45,514 of 48,557 rows."""
    archive.answers = [_archive_table()[:3]]
    archive.matching = len(_ROWS["source_id"])
    assert fetch_gaia(MAX_RADIUS_LY) == []
    assert len(archive.queries) == FETCH_ATTEMPTS
    out = capsys.readouterr().out
    assert "the archive sent 3 of 7 matching rows" in out


def test_answer_with_repeated_rows_gives_no_stars(archive, retry_waits, capsys):
    """Repeats in place of missing rows would keep the count right."""
    table = _archive_table()
    table[-1] = table[0]
    archive.answers = [table]
    assert fetch_gaia(MAX_RADIUS_LY) == []
    assert len(archive.queries) == FETCH_ATTEMPTS
    assert "the archive sent repeated rows" in capsys.readouterr().out


def test_archive_is_retried(archive, retry_waits):
    archive.answers = [ConnectionError("timed out"), _archive_table()]
    assert len(fetch_gaia(MAX_RADIUS_LY)) == len(_KEPT)
    assert len(archive.queries) == 2
    assert len(retry_waits) == 1


def test_archive_down_gives_no_stars(archive, retry_waits, capsys):
    archive.answers = [ConnectionError("503 Service Unavailable")]
    assert fetch_gaia(MAX_RADIUS_LY) == []
    assert len(archive.queries) == FETCH_ATTEMPTS
    out = capsys.readouterr().out
    assert "Gaia archive query failed: 503 Service Unavailable" in out


def test_empty_archive_answer_gives_no_stars(archive, retry_waits, capsys):
    archive.answers = [_archive_table()[:0]]
    assert fetch_gaia(MAX_RADIUS_LY) == []
    assert "No Gaia results" in capsys.readouterr().out
