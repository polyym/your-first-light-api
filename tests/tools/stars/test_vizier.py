"""Querying VizieR: retries, the CfA mirror and why an answer is empty."""

import sys
import types
from io import BytesIO
from typing import Any

import pytest
from astropy.table import MaskedColumn, Table

from tools.updaters.retry import FETCH_ATTEMPTS
from tools.updaters.stars.astrometry import min_parallax_mas
from tools.updaters.stars.gliese import fetch_gliese
from tools.updaters.stars.validate import MAX_RADIUS_LY
from tools.updaters.stars.vizier import (
    MIN_PARALLAX_SNR,
    VIZIER_HOSTS,
    query_catalogue,
    row_distance_ly,
)

CDS_HOST, CFA_HOST = VIZIER_HOSTS

# What the CfA mirror answered to an all-sky parallax cut on Gaia DR3,
# keeping one of its metadata INFO elements.
_EMPTY_ANSWER = b"""<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
<INFO name="server_software" value="VizieR/7.6.1"/>
<RESOURCE>
</RESOURCE>
<INFO name="Warning"
  value="Missing '-c' argument (Target position and geometry)"/>
<INFO name="Warning" value="Constraint added: -c=  0.000000+90.000000"/>
<RESOURCE>
</RESOURCE>
</VOTABLE>
"""


# What the CfA mirror answered, with HTTP status 200, when its database
# was unreachable.
_ERROR_ANSWER = b"""<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
<INFO name="server_software" value="VizieR/7.6.1"/>
<INFO name="Error" value=" "/>
<INFO name="Error" value=" -- no connection"/>
<INFO name="Error" value=" Report from: stdb_pg,     Status: STDB_ERR "/>
<INFO name="Error" value="Postgres connect error"/>
<RESOURCE>
</RESOURCE>
</VOTABLE>
"""


def _votable(table: Table) -> bytes:
    out = BytesIO()
    table.write(out, format="votable")
    return out.getvalue()


_ROWS = _votable(Table({"HIP": [87937], "Plx": [548.31]}))


class _Response:
    def __init__(self, content: bytes | None):
        self.content = content

    def raise_for_status(self) -> None:
        if self.content is None:
            raise ConnectionError("404 Client Error: Not Found")


class _Hosts:
    """What each VizieR host answers, and the queries each received.

    Each host gives its answers in turn and then repeats its last one;
    an answer of ``None`` is an HTTP error.
    """

    def __init__(self) -> None:
        self.answers: dict[str, list[bytes | None]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def answer(self, host: str) -> bytes | None:
        queue = self.answers[host]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def hosts_called(self) -> list[str]:
        return [host for host, _ in self.calls]


@pytest.fixture
def vizier(monkeypatch: pytest.MonkeyPatch) -> _Hosts:
    """Stands astroquery's Vizier in for the VizieR hosts."""
    hosts = _Hosts()

    class FakeVizier:
        def __init__(self, *, columns, row_limit, vizier_server):
            self.host = vizier_server

        def query_constraints_async(self, **kwargs):
            hosts.calls.append((self.host, kwargs))
            return _Response(hosts.answer(self.host))

    module = types.ModuleType("astroquery.vizier")
    module.Vizier = FakeVizier
    monkeypatch.setitem(
        sys.modules, "astroquery", types.ModuleType("astroquery")
    )
    monkeypatch.setitem(sys.modules, "astroquery.vizier", module)
    return hosts


def _query() -> Any:
    return query_catalogue(
        "HIPPARCOS", "I/239/hip_main", ["HIP", "Plx"], Plx=">20.38475"
    )


def test_cds_answer_is_used(vizier, retry_waits):
    vizier.answers[CDS_HOST] = [_ROWS]
    assert list(_query()["HIP"]) == [87937]
    assert vizier.calls == [
        (
            CDS_HOST,
            {"catalog": "I/239/hip_main", "cache": False, "Plx": ">20.38475"},
        )
    ]
    assert retry_waits == []


def test_cds_is_retried_before_the_mirror(vizier, retry_waits):
    vizier.answers[CDS_HOST] = [None, _ROWS]
    assert list(_query()["HIP"]) == [87937]
    assert vizier.hosts_called() == [CDS_HOST, CDS_HOST]
    assert len(retry_waits) == 1


def test_cfa_mirror_answers_when_cds_keeps_failing(vizier, retry_waits, capsys):
    vizier.answers[CDS_HOST] = [None]
    vizier.answers[CFA_HOST] = [_ROWS]
    assert list(_query()["HIP"]) == [87937]
    assert vizier.hosts_called() == [CDS_HOST] * FETCH_ATTEMPTS + [CFA_HOST]
    assert f"HIPPARCOS query to {CDS_HOST} failed" in capsys.readouterr().out


def test_empty_answer_moves_on_and_says_why(vizier, retry_waits, capsys):
    vizier.answers[CDS_HOST] = [_EMPTY_ANSWER]
    vizier.answers[CFA_HOST] = [_ROWS]
    assert list(_query()["HIP"]) == [87937]
    assert vizier.hosts_called() == [CDS_HOST, CFA_HOST]
    assert retry_waits == []
    out = capsys.readouterr().out
    assert f"No HIPPARCOS results from {CDS_HOST}" in out
    assert "Missing '-c' argument (Target position and geometry)" in out
    assert "VizieR/7.6.1" not in out


def test_server_error_is_retried_on_the_same_host(vizier, retry_waits):
    vizier.answers[CDS_HOST] = [_ERROR_ANSWER, _ROWS]
    assert list(_query()["HIP"]) == [87937]
    assert vizier.hosts_called() == [CDS_HOST, CDS_HOST]
    assert len(retry_waits) == 1


def test_lasting_server_error_moves_on_and_says_why(
    vizier, retry_waits, capsys
):
    vizier.answers[CDS_HOST] = [_ERROR_ANSWER]
    vizier.answers[CFA_HOST] = [_ROWS]
    assert list(_query()["HIP"]) == [87937]
    assert vizier.hosts_called() == [CDS_HOST] * FETCH_ATTEMPTS + [CFA_HOST]
    assert (
        f"HIPPARCOS query to {CDS_HOST} failed: VizieR error: "
        "-- no connection; Report from: stdb_pg, Status: STDB_ERR; "
        "Postgres connect error\n"
    ) in capsys.readouterr().out


def test_no_rows_anywhere_gives_none(vizier, retry_waits, capsys):
    vizier.answers[CDS_HOST] = [None]
    vizier.answers[CFA_HOST] = [_EMPTY_ANSWER]
    assert _query() is None
    assert "Constraint added" in capsys.readouterr().out


def _distance_ly(
    parallax: float, error: float, masked: str | None = None
) -> float | None:
    """The distance of one table row, with the named cell masked."""
    table = Table(
        {
            "Plx": MaskedColumn([parallax], mask=[masked == "Plx"]),
            "e_Plx": MaskedColumn([error], mask=[masked == "e_Plx"]),
        }
    )
    return row_distance_ly(table[0], "Plx", "e_Plx")


def test_parallax_gives_the_distance_from_five_standard_errors_up():
    """Barnard's Star in HIPPARCOS: 549.01 +- 1.58 mas."""
    assert _distance_ly(549.01, 1.58) == pytest.approx(5.9408, abs=1e-4)
    error_at_the_limit = 549.01 / MIN_PARALLAX_SNR
    assert _distance_ly(549.01, error_at_the_limit) is not None
    assert _distance_ly(549.01, error_at_the_limit + 0.01) is None


# numpy warns when a masked cell is read as a number.
@pytest.mark.filterwarnings("error")
@pytest.mark.parametrize("masked", ["Plx", "e_Plx"])
def test_row_with_a_missing_parallax_or_error_gives_no_distance(masked):
    assert _distance_ly(549.01, 1.58, masked=masked) is None


@pytest.mark.parametrize(
    ("parallax", "error"),
    [(0.0, 1.58), (549.01, 0.0), (float("nan"), 1.58), (549.01, float("nan"))],
)
def test_row_with_a_zero_or_nan_parallax_or_error_gives_no_distance(
    parallax, error
):
    assert _distance_ly(parallax, error) is None


def test_fetch_asks_for_the_exact_parallax_cut(vizier, retry_waits):
    """The cut is the parallax at 160 ly, not 20.4 mas (159.88 ly)."""
    vizier.answers[CDS_HOST] = [_EMPTY_ANSWER]
    vizier.answers[CFA_HOST] = [_EMPTY_ANSWER]
    assert fetch_gliese(MAX_RADIUS_LY) == []
    cut = min_parallax_mas(MAX_RADIUS_LY)
    assert cut == pytest.approx(20.38475)
    assert vizier.calls[0][1]["plx"] == f">{cut}"
