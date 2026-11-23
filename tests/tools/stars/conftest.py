"""Fixtures shared by the star updater's tests."""

import sys
import types
from collections.abc import Callable

import pytest
from astropy.table import Table

from tools.updaters.stars.entry import Star


def _make_star(
    name: str,
    dist: float,
    ra: float | None,
    dec: float | None,
    *,
    source: str | None = None,
    pos_source: str | None = None,
    hip: int | None = None,
    band: str = "V",
    sp: str = "M0V",
    mag: float = 10.0,
    exo: int = 0,
) -> Star:
    star = {
        "name": name,
        "distance_ly": dist,
        "spectral_type": sp,
        "apparent_magnitude": mag,
        "magnitude_band": band,
        "known_exoplanets": exo,
        "ra_deg": ra,
        "dec_deg": dec,
    }
    if source:
        star["_source"] = source
    if pos_source:
        star["_pos_source"] = pos_source
    if hip:
        star["_hip_id"] = hip
    return star


@pytest.fixture
def make_star() -> Callable[..., Star]:
    """Builds star entries with the fields every stage reads."""
    return _make_star


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
