"""Planet counts from the NASA Exoplanet Archive."""

import sys
import types

import pytest
from astropy.table import MaskedColumn, Table

from tools.updaters.retry import FETCH_ATTEMPTS
from tools.updaters.stars.exoplanets import (
    fetch_exoplanet_counts,
    match_exoplanets,
)

_PROXIMA_GAIA = "Gaia DR3 5853498713190525696"
_GJ_3323_GAIA = "Gaia DR3 3187115498866675456"


def _archive_table() -> Table:
    """One row per planet: two of Proxima Centauri's, one of GJ 3323's."""
    return Table(
        {
            "hostname": ["Proxima Cen", "GJ 3323", "Proxima Cen"],
            "hip_name": MaskedColumn(
                ["HIP 70890", "", "HIP 70890"], mask=[False, True, False]
            ),
            "hd_name": MaskedColumn(["", "", ""], mask=[True, True, True]),
            "gaia_dr3_id": [_PROXIMA_GAIA, _GJ_3323_GAIA, _PROXIMA_GAIA],
        }
    )


class _Archive:
    """The queries sent, and the answers to give: a table or an error."""

    def __init__(self) -> None:
        self.queries: list[dict[str, str]] = []
        self.answers: list[Table | Exception] = []

    def query_criteria(self, **kwargs: str) -> Table:
        self.queries.append(kwargs)
        queue = self.answers
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def archive(monkeypatch: pytest.MonkeyPatch) -> _Archive:
    """Stands astroquery's NasaExoplanetArchive in for the archive."""
    archive = _Archive()
    name = "astroquery.ipac.nexsci.nasa_exoplanet_archive"
    module = types.ModuleType(name)
    module.NasaExoplanetArchive = archive
    monkeypatch.setitem(
        sys.modules, "astroquery", types.ModuleType("astroquery")
    )
    monkeypatch.setitem(sys.modules, name, module)
    return archive


def test_archive_is_retried(archive, retry_waits):
    archive.answers = [ConnectionError("timed out"), _archive_table()]
    assert fetch_exoplanet_counts() == {
        "Proxima Cen": 2,
        "HIP 70890": 2,
        _PROXIMA_GAIA: 2,
        "GJ 3323": 1,
        _GJ_3323_GAIA: 1,
    }
    assert len(archive.queries) == 2
    assert len(retry_waits) == 1


def test_query_asks_for_the_columns_the_counts_are_read_from(archive):
    table = _archive_table()
    archive.answers = [table]

    fetch_exoplanet_counts()

    (query,) = archive.queries
    assert query["table"] == "pscomppars"
    assert query["select"].split(",") == table.colnames


def test_each_host_counts_its_own_planets(archive):
    """HD 133131 A has two planets and B one; HIPPARCOS lists the pair once."""
    archive.answers = [
        Table(
            {
                "hostname": ["HD 133131 A", "HD 133131 A", "HD 133131 B"],
                "hip_name": ["HIP 73674 A", "HIP 73674 A", "HIP 73674 B"],
                "hd_name": ["HD 133131 A", "HD 133131 A", "HD 133131 B"],
                "gaia_dr3_id": ["Gaia DR3 1", "Gaia DR3 1", "Gaia DR3 2"],
            }
        )
    ]
    assert fetch_exoplanet_counts() == {
        "HD 133131 A": 2,
        "HIP 73674 A": 2,
        "Gaia DR3 1": 2,
        "HD 133131 B": 1,
        "HIP 73674 B": 1,
        "Gaia DR3 2": 1,
        "HIP 73674": 3,
    }


def test_gaia_source_of_an_unresolved_pair_counts_both_hosts(archive):
    """HD 41004 A and B, half an arcsecond apart, have a planet each.

    The archive gives the pair's one Gaia source to B alone.
    """
    archive.answers = [
        Table(
            {
                "hostname": ["HD 41004 A", "HD 41004 B"],
                "hip_name": ["HIP 28393 A", "HIP 28393 B"],
                "hd_name": ["HD 41004 A", "HD 41004 B"],
                "gaia_dr3_id": MaskedColumn(
                    ["", "Gaia DR3 4794830231453653888"], mask=[True, False]
                ),
            }
        )
    ]
    counts = fetch_exoplanet_counts()
    assert counts["Gaia DR3 4794830231453653888"] == 2
    assert counts["HIP 28393"] == 2
    assert counts["HD 41004 B"] == 1


def test_gaia_source_finds_a_host_the_archive_names_differently(make_star):
    """L 98-59 is a Gaia row alone here; LHS 1140 is NN 3053 in Gliese."""
    gaia_only = make_star("Gaia DR3 5271055243163629056", 34.6, 124.5, -68.3)
    gaia_only["_gaia_id"] = "5271055243163629056"
    merged = make_star("NN 3053", 48.8, 11.2, -15.3)
    merged["_gaia_id"] = "2371032916186181760"
    counts = {
        "L 98-59": 5,
        "Gaia DR3 5271055243163629056": 5,
        "LHS 1140": 2,
        "Gaia DR3 2371032916186181760": 2,
    }

    assert match_exoplanets([gaia_only, merged], counts) == 2
    assert [s["known_exoplanets"] for s in (gaia_only, merged)] == [5, 2]


def test_gaia_source_wins_over_a_hip_number_a_pair_shares(make_star):
    star = make_star("HIP 73674", 154.4, 225.9, -27.8, hip=73674)
    star["_gaia_id"] = "1"

    match_exoplanets([star], {"HIP 73674": 3, "Gaia DR3 1": 2})

    assert star["known_exoplanets"] == 2


def test_curated_star_takes_its_planets_under_the_archive_name(make_star):
    """Struve 2398 A and B are "Gl 725 A" and "Gl 725 B" to the archive."""
    stars = [
        make_star("Struve 2398 A", 11.525, 280.6946, 59.6304),
        make_star("Struve 2398 B", 11.525, 280.6954, 59.6269),
    ]

    assert match_exoplanets(stars, {"Gl 725 A": 1, "Gl 725 B": 1}) == 2
    assert [s["known_exoplanets"] for s in stars] == [1, 1]


def test_host_with_no_designation_in_the_archive_is_found_by_alias(make_star):
    """TOI-5997 is HIP 85850, which the archive does not say."""
    star = make_star("HIP 85850", 152.0551, 263.1537, 33.5698, hip=85850)
    star["_gaia_id"] = "4602034956332491264"

    assert match_exoplanets([star], {"TOI-5997": 1}) == 1
    assert star["known_exoplanets"] == 1


def _proxima(make_star):
    star = make_star("Proxima Centauri", 4.2465, 217.4289, -62.6795, hip=70890)
    star["_gaia_id"] = "5853498713190525696"
    return star


# The keys Proxima Centauri is looked up by, in the order they are tried.
_PROXIMA_KEYS = (
    _PROXIMA_GAIA,
    "Proxima Centauri",
    "Proxima Cen",
    "GJ 551",
    "Gl 551",
    "HIP 70890",
    "HIP70890",
)


@pytest.mark.parametrize("key", _PROXIMA_KEYS)
def test_host_is_found_by_gaia_source_name_alias_or_hip_number(make_star, key):
    star = _proxima(make_star)

    assert match_exoplanets([star], {key: 2}) == 1
    assert star["known_exoplanets"] == 2


@pytest.mark.parametrize("first", range(len(_PROXIMA_KEYS) - 1))
def test_first_key_the_archive_lists_gives_the_count(make_star, first):
    star = _proxima(make_star)
    counts = {key: n + 1 for n, key in enumerate(_PROXIMA_KEYS) if n >= first}

    match_exoplanets([star], counts)

    assert star["known_exoplanets"] == first + 1


def test_star_the_archive_does_not_list_keeps_its_count(make_star):
    star = _proxima(make_star)
    star["known_exoplanets"] = 3
    counts = {"Barnard's star": 4, "HIP 87937": 4, "Gaia DR3 1": 4}

    assert match_exoplanets([star], counts) == 0
    assert star["known_exoplanets"] == 3


def test_archive_down_gives_no_counts(archive, retry_waits, capsys):
    archive.answers = [ConnectionError("503 Service Unavailable")]
    assert fetch_exoplanet_counts() == {}
    assert len(archive.queries) == FETCH_ATTEMPTS
    out = capsys.readouterr().out
    assert "Exoplanet Archive query failed: 503 Service Unavailable" in out
