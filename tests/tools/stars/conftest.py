"""Fixtures shared by the star updater's tests."""

from collections.abc import Callable

import pytest

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
