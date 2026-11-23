"""The checks that fail the run rather than write a wrong catalogue."""

import json

import pytest

from tools.updaters.stars.curated import (
    EXTRA_STARS,
    KNOWN_STAR_OVERRIDES,
    REFERENCE_GAIA_MATCHES,
    REFERENCE_POSITIONS,
)
from tools.updaters.stars.merge import apply_overrides
from tools.updaters.stars.validate import (
    MIN_FETCH_COUNTS,
    check_fetch_counts,
    check_reference_matches,
    check_reference_positions,
    find_positional_duplicates,
    validate_catalogue,
)
from tools.updaters.stars.write import STARS_PATH


@pytest.mark.parametrize(
    "gliese_dec",
    [-66.1820, -66.1818],
    ids=["designation-to-the-south", "designation-to-the-north"],
)
def test_detects_disagreeing_distance_duplicate(make_star, gliese_dec):
    stars = [
        make_star("Delta Pavonis", 19.893, 302.1830, -66.1819),
        make_star("Vega", 25.04, 279.2347, 38.7837),
        make_star("Gl 780", 18.62, 302.1831, gliese_dec),
    ]
    pairs = find_positional_duplicates(stars)
    assert len(pairs) == 1
    i, j, _sep = pairs[0]
    assert {stars[i]["name"], stars[j]["name"]} == {"Delta Pavonis", "Gl 780"}


def test_same_source_resolved_double_is_exempt(make_star):
    """HIP 34085 and 34087: one catalogue resolved them, noisy parallaxes.

    Two rows of one catalogue are two real stars even when their
    distances disagree.
    """
    stars = [
        make_star(
            "HIP 34085", 121.2927, 104.0, -25.0, source="hipparcos", hip=34085
        ),
        make_star(
            "HIP 34087",
            110.4864,
            104.0,
            -25.0036,
            source="hipparcos",
            hip=34087,
        ),
    ]
    assert find_positional_duplicates(stars) == []


def test_written_source_field_is_recognised(make_star):
    """The written file says ``source``, not ``_source``."""
    a = make_star("HIP 34085", 121.2927, 104.0, -25.0)
    b = make_star("HIP 34087", 110.4864, 104.0, -25.0036)
    a["source"] = "hipparcos"
    b["source"] = "hipparcos"
    assert find_positional_duplicates([a, b]) == []


def test_written_sources_list_is_recognised(make_star):
    """A pair sharing any catalogue in ``sources`` is a real pair."""
    a = make_star("HIP 79242", 111.7007, 242.5626, -84.2316)
    b = make_star("Gl 606.1", 83.6297, 242.569, -84.2315)
    a["sources"] = ["gaia", "gliese", "hipparcos"]
    b["sources"] = ["gliese"]
    assert find_positional_duplicates([a, b]) == []


def test_disjoint_sources_are_still_flagged(make_star):
    a = make_star("HIP 1", 111.7, 242.5626, -84.2316)
    b = make_star("Gl 2", 83.6, 242.569, -84.2315)
    a["sources"] = ["hipparcos"]
    b["sources"] = ["gliese"]
    assert len(find_positional_duplicates([a, b])) == 1


def test_pair_agreeing_in_distance_is_exempt(make_star):
    """Components of one system, each from its own catalogue."""
    stars = [
        make_star("HIP 1", 20.0, 242.5626, -84.2316, source="hipparcos"),
        make_star("Gl 2", 20.8, 242.569, -84.2315, source="gliese"),
    ]
    assert find_positional_duplicates(stars) == []


def test_pair_of_common_names_is_exempt(make_star):
    """Curated components of one system, whatever their distances."""
    stars = [
        make_star("Sirius A", 8.6, 101.2872, -16.7161),
        make_star("Sirius B", 9.8, 101.2875, -16.7163),
    ]
    assert find_positional_duplicates(stars) == []


def test_pair_too_far_apart_in_magnitude_is_not_a_duplicate(make_star):
    """HIP 2237, V 6.44, and a V 20.66 Gaia row 14.9 arcsec from it."""
    stars = [
        make_star(
            "HIP 2237",
            105.1777,
            7.0879,
            -20.3351,
            source="hipparcos",
            hip=2237,
            mag=6.44,
        ),
        make_star(
            "Gaia DR3 2363291087311784832",
            114.0433,
            7.0923,
            -20.3351,
            source="gaia",
            mag=20.66,
        ),
    ]
    assert find_positional_duplicates(stars) == []


def test_validate_catalogue_fails_on_positional_dup(make_star):
    stars = [
        make_star("Delta Pavonis", 19.893, 302.1830, -66.1819),
        make_star("Gl 780", 18.62, 302.1831, -66.1820),
    ]
    errors = [
        e for e in validate_catalogue(stars) if e.startswith("POSITIONAL_DUP")
    ]
    assert len(errors) == 1
    assert "Gl 780" in errors[0]


def test_no_positional_duplicates_in_shipped_catalogue():
    stars = json.loads(STARS_PATH.read_text(encoding="utf-8"))
    pairs = find_positional_duplicates(stars)
    sample = [(stars[i]["name"], stars[j]["name"]) for i, j, _ in pairs[:5]]
    assert not pairs, f"{len(pairs)} positional duplicates, e.g. {sample}"


def test_healthy_fetch_counts_pass():
    assert (
        check_fetch_counts({"hipparcos": 6497, "gliese": 3148, "gaia": 48418})
        == []
    )
    assert check_fetch_counts({"exoplanet_archive": 5643}) == []


def test_fetch_exactly_at_its_floor_passes():
    assert check_fetch_counts(dict(MIN_FETCH_COUNTS)) == []


def test_thin_source_is_rejected():
    errors = check_fetch_counts(
        {"hipparcos": 6497, "gliese": 3148, "gaia": 512}
    )
    assert len(errors) == 1
    assert "gaia" in errors[0]
    assert "512" in errors[0]


def test_failed_sources_are_rejected():
    """A fetcher that failed returns nothing; that must stop the run."""
    errors = check_fetch_counts({"hipparcos": 0, "gliese": 0, "gaia": 0})
    assert len(errors) == 3


def test_thin_exoplanet_archive_is_rejected():
    errors = check_fetch_counts({"exoplanet_archive": 0})
    assert len(errors) == 1
    assert "exoplanet_archive" in errors[0]


def _reference_stars(make_star, source, moved=None):
    stars = []
    for cid, (ra, dec) in REFERENCE_POSITIONS[source].items():
        if moved and cid == moved[0]:
            ra, dec = moved[1]
        star = make_star(cid, 10.0, ra, dec, source=source)
        star["_catalogue_id"] = cid
        stars.append(star)
    return stars


def test_reference_stars_in_place_pass(make_star):
    for source in ("hipparcos", "gliese", "gaia"):
        stars = _reference_stars(make_star, source)
        assert check_reference_positions(stars, source) == []


def test_reference_star_at_wrong_epoch_is_rejected(make_star):
    """Gl 451 A at its B1950-epoch position, 350 arcsec from J2000."""
    stars = _reference_stars(
        make_star, "gliese", moved=("Gl 451 A", (178.1738, 37.8002))
    )
    errors = check_reference_positions(stars, "gliese")
    assert len(errors) == 1
    assert "Gl 451 A" in errors[0]
    assert "epoch" in errors[0]


def test_missing_reference_star_is_rejected():
    errors = check_reference_positions([], "hipparcos")
    assert len(errors) == 3
    assert all("did not return" in e for e in errors)


def _spectral_type_errors(stars):
    return [
        e for e in validate_catalogue(stars) if e.startswith("SPECTRAL_TYPE")
    ]


def test_capella_as_an_m_dwarf_fails_validation(make_star):
    """HIPPARCOS gives Capella, V 0.08 at 42.199 ly, the type M1: comp."""
    capella = make_star(
        "HIP 24608",
        42.199,
        79.1723,
        45.998,
        source="hipparcos",
        hip=24608,
        sp="M1: comp",
        mag=0.08,
    )
    errors = _spectral_type_errors([capella])
    assert len(errors) == 1
    assert "'HIP 24608' has type 'M1: comp'" in errors[0]


def test_curated_stars_pass_every_check():
    """The hand-verified overrides and extra stars are a correct catalogue."""
    stars = [dict(s) for s in EXTRA_STARS] + [
        {"name": name, **values}
        for name, values in KNOWN_STAR_OVERRIDES.items()
    ]
    assert validate_catalogue(stars) == []


def test_catalogue_without_the_overridden_stars_fails_validation():
    assert validate_catalogue([]) == [
        f"MISSING: '{name}' not in catalogue" for name in KNOWN_STAR_OVERRIDES
    ]


def test_repeated_name_fails_validation(make_star):
    stars = [
        make_star("HIP 1", 10.0, 10.0, 10.0),
        make_star("HIP 2", 20.0, 50.0, 50.0),
        make_star("HIP 1", 30.0, 90.0, -10.0),
    ]
    errors = [e for e in validate_catalogue(stars) if e.startswith("DUPLICATE")]
    assert errors == ["DUPLICATE: 'HIP 1' at indices 0 and 2"]


def _range_errors(stars):
    return [e for e in validate_catalogue(stars) if e.startswith("RANGE")]


@pytest.mark.parametrize(
    ("values", "error"),
    [
        ({"distance_ly": 0.0}, "distance 0.0 outside (0, 160]"),
        ({"distance_ly": 160.1}, "distance 160.1 outside (0, 160]"),
        ({"apparent_magnitude": -2.0}, "magnitude -2.0 outside (-2, 30)"),
        ({"apparent_magnitude": 30.0}, "magnitude 30.0 outside (-2, 30)"),
        ({"ra_deg": -0.1}, "RA -0.1 outside [0, 360)"),
        ({"ra_deg": 360.0}, "RA 360.0 outside [0, 360)"),
        ({"dec_deg": -90.1}, "Dec -90.1 outside [-90, 90]"),
        ({"dec_deg": 90.1}, "Dec 90.1 outside [-90, 90]"),
    ],
    ids=[
        "no-distance",
        "beyond-the-catalogue",
        "too-bright",
        "too-faint",
        "ra-below-0",
        "ra-360",
        "dec-below-the-pole",
        "dec-above-the-pole",
    ],
)
def test_value_outside_its_range_fails_validation(make_star, values, error):
    star = {**make_star("HIP 1", 10.0, 10.0, 10.0), **values}
    assert _range_errors([star]) == [f"RANGE: 'HIP 1' {error}"]


def test_values_at_the_ends_of_each_range_pass(make_star):
    stars = [
        make_star("HIP 1", 160.0, 0.0, -90.0, mag=29.9),
        make_star("HIP 2", 0.1, 359.9999, 90.0, mag=-1.9),
        make_star("HIP 3", 10.0, None, None),
    ]
    assert _range_errors(stars) == []


def test_override_on_wrong_star_is_flagged(make_star):
    """Kapteyn's Star's override landing on HIP 86990 (GJ 693).

    A wrong name mapping would make the override overwrite GJ 693 with
    Kapteyn's data while the real Kapteyn's Star stayed as HIP 24186.
    """
    s = make_star(
        "Kapteyn's Star",
        18.954,
        266.6426,
        -57.3190,
        source="hipparcos",
        hip=86990,
    )
    assert apply_overrides([s]) == 1
    errors = [
        e for e in validate_catalogue([s]) if e.startswith("OVERRIDE_MISMATCH")
    ]
    assert len(errors) == 1
    assert "Kapteyn's Star" in errors[0]


def test_override_on_right_star_passes(make_star):
    s = make_star(
        "Kapteyn's Star",
        12.8308,
        77.9191,
        -45.0184,
        source="hipparcos",
        hip=24186,
    )
    apply_overrides([s])
    assert s["distance_ly"] == 12.777
    assert not [
        e for e in validate_catalogue([s]) if e.startswith("OVERRIDE_MISMATCH")
    ]


def _hipparcos_references(gaia_ids: dict[str, str | None]) -> list[dict]:
    stars = []
    for cid, gaia_id in gaia_ids.items():
        star = {"_catalogue_id": cid}
        if gaia_id:
            star["_gaia_id"] = gaia_id
        stars.append(star)
    return stars


def test_hipparcos_references_with_their_gaia_matches_pass():
    stars = _hipparcos_references(dict(REFERENCE_GAIA_MATCHES))
    assert check_reference_matches(stars) == []


def test_hipparcos_reference_without_its_gaia_match_fails():
    """As every star would be, were Gaia's match table missing."""
    gaia_ids: dict[str, str | None] = dict(REFERENCE_GAIA_MATCHES)
    gaia_ids["87937"] = None
    (error,) = check_reference_matches(_hipparcos_references(gaia_ids))
    assert error.startswith("MATCH: hipparcos 87937 lacks its Gaia DR3 match")


def test_hipparcos_reference_with_another_match_fails():
    gaia_ids: dict[str, str | None] = dict(REFERENCE_GAIA_MATCHES)
    gaia_ids["24186"] = "1"
    assert len(check_reference_matches(_hipparcos_references(gaia_ids))) == 1
