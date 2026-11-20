"""The order of the updater's steps."""

import pytest

from tools.updaters.stars import main
from tools.updaters.stars.curated import KNOWN_STAR_OVERRIDES
from tools.updaters.stars.entry import Star
from tools.updaters.stars.validate import MIN_FETCH_COUNTS

_OVERRIDE_PLANETS: int = KNOWN_STAR_OVERRIDES["Barnard's Star"][
    "known_exoplanets"
]


def _planets_written_for_barnards_star(
    monkeypatch: pytest.MonkeyPatch, make_star, archive_counts: dict[str, int]
) -> int:
    """Runs the updater on one HIPPARCOS row and a stand-in archive."""
    barnard = make_star(
        "Barnard's Star",
        5.9408,
        269.4521,
        4.6934,
        source="hipparcos",
        hip=87937,
    )
    floor = MIN_FETCH_COUNTS["exoplanet_archive"]
    counts = {f"host {n}": 1 for n in range(floor)} | archive_counts
    written: list[Star] = []
    monkeypatch.setattr(main, "_fetch_catalogues", lambda: [[barnard]])
    monkeypatch.setattr(main, "fetch_exoplanet_counts", lambda: counts)
    monkeypatch.setattr(main, "validate_catalogue", lambda stars: [])
    monkeypatch.setattr(
        main, "write_stars", lambda stars: written.extend(stars) or True
    )

    main.main()

    planets = {s["name"]: s["known_exoplanets"] for s in written}
    return planets["Barnard's Star"]


def test_archive_planet_count_wins_over_an_override(monkeypatch, make_star):
    archive_planets = _OVERRIDE_PLANETS + 1
    assert (
        _planets_written_for_barnards_star(
            monkeypatch, make_star, {"HIP 87937": archive_planets}
        )
        == archive_planets
    )


def test_override_planet_count_stands_for_a_star_the_archive_lacks(
    monkeypatch, make_star
):
    assert (
        _planets_written_for_barnards_star(monkeypatch, make_star, {})
        == _OVERRIDE_PLANETS
    )
