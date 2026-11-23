"""The order of the updater's steps."""

import pytest

from tools.updaters.stars import main
from tools.updaters.stars.curated import (
    KNOWN_STAR_OVERRIDES,
    REFERENCE_POSITIONS,
)
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


def test_component_of_a_star_beyond_the_edge_leaves_with_it(
    monkeypatch, make_star
):
    """Tau Ophiuchi: 55.9 ly by Gliese, about 180 by Gaia.

    HIPPARCOS star HIP 1 takes its Gaia match's 179 ly and absorbs
    Gl 9 A; Gl 9 B, too far for the merge, takes the system's distance.
    The merge's cut then drops both.
    """
    barnard = make_star(
        "Barnard's Star",
        5.9408,
        269.4521,
        4.6934,
        source="hipparcos",
        hip=87937,
    )
    hip = make_star(
        "HIP 1",
        179.0,
        10.0,
        10.0,
        source="hipparcos",
        pos_source="hipparcos",
        hip=1,
        mag=5.2,
    )
    hip["_gaia_id"] = "11"
    gliese = []
    for comp, ra, mag in (("A", 10.0, 5.2), ("B", 10.02, 5.9)):
        row = make_star(
            f"Gl 9 {comp}",
            55.9,
            ra,
            10.0,
            source="gliese",
            pos_source="gliese",
            mag=mag,
        )
        row["_gliese_system"] = "Gl 9"
        gliese.append(row)
    floor = MIN_FETCH_COUNTS["exoplanet_archive"]
    written: list[Star] = []
    monkeypatch.setattr(
        main, "_fetch_catalogues", lambda: [[barnard, hip], gliese]
    )
    monkeypatch.setattr(
        main,
        "fetch_exoplanet_counts",
        lambda: {f"host {n}": 1 for n in range(floor)},
    )
    monkeypatch.setattr(main, "validate_catalogue", lambda stars: [])
    monkeypatch.setattr(
        main, "write_stars", lambda stars: written.extend(stars) or True
    )

    main.main()

    names = {s["name"] for s in written}
    assert "Barnard's Star" in names
    assert not names & {"HIP 1", "Gl 9 A", "Gl 9 B"}


def test_hipparcos_fetch_without_its_gaia_matches_stops_the_run(
    monkeypatch, capsys
):
    """As it would if the archive's match table went missing."""

    def references(source: str) -> list[Star]:
        return [
            {"_catalogue_id": cid, "ra_deg": ra, "dec_deg": dec}
            for cid, (ra, dec) in REFERENCE_POSITIONS[source].items()
        ]

    written: list[Star] = []
    monkeypatch.setattr(
        main, "fetch_hipparcos", lambda _: references("hipparcos")
    )
    monkeypatch.setattr(main, "fetch_gliese", lambda _: references("gliese"))
    monkeypatch.setattr(main, "fetch_gaia", lambda _: references("gaia"))
    monkeypatch.setattr(main, "check_fetch_counts", lambda counts: [])
    monkeypatch.setattr(main, "write_stars", written.extend)

    with pytest.raises(SystemExit) as stopped:
        main.main()

    assert stopped.value.code == 1
    out = capsys.readouterr().out
    assert out.count("MATCH: hipparcos") == len(
        REFERENCE_POSITIONS["hipparcos"]
    )
    assert "Data NOT written" in out
    assert written == []
