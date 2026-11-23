"""Gaia photometry, spectral classes from colour and type choice."""

import pytest

from first_light.facts.stars import GIANT_TYPE, classify_spectral
from tools.updaters.stars.merge import merge_catalogues
from tools.updaters.stars.photometry import (
    GIANT_LUMINOSITY_TYPE,
    MISSING_MAGNITUDE,
    SpectralTypeFixes,
    absolute_magnitude,
    contradicts_magnitude,
    estimate_spectral_class,
    fix_spectral_types,
    gaia_g_to_v,
    normalise_spectral_type,
    remove_unknown_magnitudes,
    temperature_class,
)
from tools.updaters.stars.validate import MAX_RADIUS_LY, validate_catalogue


def test_solar_colour_is_g():
    assert estimate_spectral_class(0.82, 4.8, 32.6) == "G (est)"


def test_red_dwarf_colour_is_m():
    assert estimate_spectral_class(3.1, 14.0, 30.0) == "M (est)"


def test_faint_blue_object_is_white_dwarf():
    """Sirius B: blue, yet about magnitude 8.5 at only 8.6 ly."""
    assert estimate_spectral_class(-0.1, 8.5, 8.6) == "D (est)"


def test_missing_colour_gives_no_estimate():
    assert estimate_spectral_class(None, 10.0, 30.0) == ""


def test_red_dwarf_redder_than_bp_rp_5_is_still_m():
    """Gaia DR3 2091177593123254016: BP-RP 5.151, G 14.851, 18.5534 ly.

    LSR J1835+3259, M8.5V. By hand its absolute G is 16.08, brighter
    than the faintest red dwarf.
    """
    assert estimate_spectral_class(5.151, 14.851, 18.5534) == "M (est)"


@pytest.mark.parametrize(
    ("gmag", "expected"),
    [(18.9, "M (est)"), (19.1, "")],
    ids=["g-18.9", "g-19.1"],
)
def test_colour_fainter_than_g_19_gives_no_estimate(gmag, expected):
    """BP-RP 3.0 at 120 ly is an M dwarf at either G.

    By hand, G - V is -1.54 and the distance modulus 2.83, so absolute
    V is 17.6 or 17.8, and absolute G 16.07 or 16.27.
    """
    assert estimate_spectral_class(3.0, gmag, 120.0) == expected


def test_k_colour_too_faint_for_a_k_dwarf_gives_no_estimate():
    """The G 15.92 row 13.6 arcsec from Dubhe, BP-RP 1.593, at 129.31 ly.

    By hand its V is 16.41 and its absolute V 13.42, 4.9 mag fainter
    than the faintest K dwarf (K9V, 8.56).
    """
    assert estimate_spectral_class(1.593, 15.92, 129.31) == ""


def test_m_colour_far_brighter_than_an_m_dwarf_gives_no_estimate():
    """BP-RP 2.0 at G 3.0 and 100 ly: by hand, absolute V 1.31, a giant."""
    assert estimate_spectral_class(2.0, 3.0, 100.0) == ""


def test_red_row_too_faint_for_a_red_dwarf_needs_a_strong_parallax():
    """Gaia DR3 4752399493622045696: BP-RP 4.873, G 18.573, 15.8771 ly.

    By hand its absolute G is 20.14, past M9.5V's 16.40, so it is no
    red dwarf; with no parallax given, it is no brown dwarf either.
    """
    assert estimate_spectral_class(4.873, 18.573, 15.8771) == ""


@pytest.mark.parametrize(
    ("bp_rp", "gmag", "dist_ly", "parallax_snr"),
    [
        (4.873, 18.573, 15.8771, 1106.0),
        (3.51, 20.01, 17.0018, 458.0),
        (1.98, 20.44, 18.7419, 92.0),
    ],
    ids=["g-18.6", "g-20.0-past-the-colour-limit", "bluest-red-row"],
)
def test_red_row_far_fainter_than_any_red_dwarf_is_a_brown_dwarf(
    bp_rp, gmag, dist_ly, parallax_snr
):
    """Gaia DR3 4752399493622045696, 5278042880077383040, 6305165514134625024.

    Absolute G 20.14, 21.42 and 21.64, all well past M9.5V's 16.40.
    """
    assert (
        estimate_spectral_class(bp_rp, gmag, dist_ly, parallax_snr) == "L (est)"
    )


@pytest.mark.parametrize(
    ("bp_rp", "abs_g", "parallax_snr", "expected"),
    [
        (3.5, 16.39, 100.0, "M (est)"),
        (3.5, 16.41, 100.0, "L (est)"),
        (3.5, 16.41, 49.9, ""),
        (3.5, 20.0, 49.9, ""),
        (3.5, 20.0, 50.0, "L (est)"),
        (3.5, 20.0, None, ""),
        (1.83, 19.0, 100.0, ""),
        (1.84, 19.0, 100.0, "L (est)"),
    ],
    ids=[
        "faintest-red-dwarf",
        "past-the-faintest-red-dwarf",
        "past-it-with-a-weaker-parallax",
        "parallax-under-50-errors",
        "parallax-of-50-errors",
        "parallax-unknown",
        "orange",
        "red",
    ],
)
def test_brown_dwarf_estimate_needs_red_faint_and_a_strong_parallax(
    bp_rp, abs_g, parallax_snr, expected
):
    """At 10 pc, so G is the absolute G."""
    estimate = estimate_spectral_class(bp_rp, abs_g, 32.6156, parallax_snr)
    assert estimate == expected


def test_blue_star_below_the_white_dwarf_sequence_gives_no_estimate():
    """Absolute G 17.0 (G 17.0 at 10 pc), fainter than any white dwarf."""
    assert estimate_spectral_class(0.5, 17.0, 32.6156) == ""


def test_cool_white_dwarf_is_estimated_from_a_strong_parallax():
    """Gaia DR3 2202703050401536000, a DAH white dwarf at 27.6 ly.

    BP-RP 1.051, G 14.373, parallax of 7,615 standard errors. By hand
    its absolute G is 14.74, far below a K dwarf of that colour.
    """
    assert estimate_spectral_class(1.051, 14.373, 27.604, 7615) == "D (est)"


@pytest.mark.parametrize(
    ("bp_rp", "abs_g", "parallax_snr", "expected"),
    [
        (1.99, 14.0, 50.0, "D (est)"),
        (2.0, 14.0, 50.0, "M (est)"),
        (1.5, 14.0, 49.9, ""),
        (1.5, 12.0, 50.0, ""),
        (1.5, 12.01, 50.0, "D (est)"),
        (1.5, 16.5, 50.0, "D (est)"),
        (1.5, 16.51, 50.0, ""),
    ],
    ids=[
        "just-blue-enough",
        "too-red",
        "parallax-under-50-errors",
        "too-bright",
        "just-faint-enough",
        "end-of-the-sequence",
        "past-the-end",
    ],
)
def test_cool_white_dwarf_estimate_needs_its_colour_magnitude_and_parallax(
    bp_rp, abs_g, parallax_snr, expected
):
    """At 10 pc, so G is the absolute G."""
    estimate = estimate_spectral_class(bp_rp, abs_g, 32.6156, parallax_snr)
    assert estimate == expected


def test_estimates_group_in_api_breakdown():
    """The API must file each estimate under its class."""
    assert classify_spectral("M (est)") == "Red dwarf (M)"
    assert classify_spectral("D (est)") == "White dwarf (D)"
    assert classify_spectral("L (est)") == "Brown dwarf (L)"


def test_red_star_v_is_fainter_than_g():
    v = gaia_g_to_v(10.0, 3.0)
    assert v is not None
    assert v > 11.0


def test_solar_colour_v_is_close_to_g():
    v = gaia_g_to_v(10.0, 0.82)
    assert v is not None
    assert abs(v - 10.0) < 0.3


# G - V from the relation's published coefficients: -0.0681 at a BP-RP
# of -0.4, -0.2141 at 1 and -0.7469 at 2.
@pytest.mark.parametrize(
    ("bp_rp", "v"),
    [(-0.4, 10.0681), (1.0, 10.2141), (2.0, 10.7469)],
    ids=["blue", "orange", "red"],
)
def test_v_follows_the_published_relation(bp_rp, v):
    assert gaia_g_to_v(10.0, bp_rp) == pytest.approx(v, abs=0.0001)


@pytest.mark.parametrize(
    "bp_rp", [5.5, 5.0, -0.5, None], ids=["red", "5.0", "-0.5", "none"]
)
def test_out_of_range_colour_gives_no_v(bp_rp):
    assert gaia_g_to_v(10.0, bp_rp) is None


@pytest.mark.parametrize(
    ("dist_ly", "absolute"),
    [(32.6156, 5.0), (326.156, 0.0), (3.26156, 10.0)],
    ids=["10-parsecs", "100-parsecs", "1-parsec"],
)
def test_absolute_magnitude_is_the_magnitude_at_10_parsecs(dist_ly, absolute):
    assert absolute_magnitude(5.0, dist_ly) == pytest.approx(absolute)


def test_entries_without_a_magnitude_are_dropped(make_star):
    stars = [
        make_star("HIP 1", 10.0, 1.0, 1.0),
        make_star("Gl 2", 11.0, 2.0, 2.0, mag=MISSING_MAGNITUDE),
        make_star("HIP 3", 12.0, 3.0, 3.0),
    ]

    assert remove_unknown_magnitudes(stars) == 1
    assert [s["name"] for s in stars] == ["HIP 1", "HIP 3"]


@pytest.mark.parametrize(
    ("catalogued", "normalised"),
    [
        ("M3   V", "M3 V"),
        ("dM5.5e", "M5.5e"),
        ("K2 V J", "K2 V"),
        ("k-m", "K-M"),
        ("m+", "M+"),
        ("sdM1", "sdM1"),
        ("DA5", "DA5"),
        ("G2V", "G2V"),
    ],
    ids=[
        "repeated-spaces",
        "dwarf-prefix",
        "binary-flag",
        "lower-case-range",
        "lower-case-class",
        "subdwarf-prefix-kept",
        "white-dwarf-kept",
        "as-it-is",
    ],
)
def test_type_is_rewritten_as_the_api_reads_it(catalogued, normalised):
    assert normalise_spectral_type(catalogued) == normalised


@pytest.mark.parametrize(
    "placeholder", ["R...", "O...", "WN..."], ids=["r", "o", "wn"]
)
def test_placeholder_types_are_cleared(placeholder):
    assert normalise_spectral_type(placeholder) == ""


@pytest.mark.parametrize(
    ("spectral_type", "abs_v", "expected"),
    [
        # HIPPARCOS V 0.08 at 42.199 ly.
        ("M1: comp", -0.48, True),
        ("M4III", -0.5, False),
        ("K0", 3.0, False),
        # GJ 674 as HIPPARCOS has it: V 9.38 at 14.7964 ly.
        ("K5", 11.10, True),
        # The faintest K dwarf, K9V, is 8.56; the margin is 2 mag.
        ("K9V", 10.5, False),
        ("K9V", 10.6, True),
        ("M (est)", 22.0, True),
        ("sdM1", 13.0, False),
        ("DA2", 11.18, False),
        ("L7.5", 24.4, False),
        # AB Doradus, a K dwarf: HIPPARCOS V 6.88 at 48.69 ly.
        ("K1III(p)", 6.0, True),
        # Pollux.
        ("K0IIIb", 1.1, False),
        ("F2III-IV", 3.65, False),
        # An uncertain class keeps the dwarf label, so the dwarf range holds.
        ("K2:III:", 6.0, False),
    ],
    ids=[
        "capella-as-m-dwarf",
        "m-giant",
        "k-without-luminosity-class",
        "gj-674-as-k5",
        "k9-within-margin",
        "k9-beyond-margin",
        "fainter-than-any-m-dwarf",
        "subdwarf",
        "white-dwarf",
        "brown-dwarf",
        "giant-class-on-a-k-dwarf",
        "k-giant",
        "giant-class-within-the-margin",
        "uncertain-giant-class",
    ],
)
def test_types_ruled_out_by_absolute_magnitude(spectral_type, abs_v, expected):
    assert contradicts_magnitude(spectral_type, abs_v) is expected


def test_giant_class_is_read_as_the_api_reads_it():
    assert GIANT_LUMINOSITY_TYPE.pattern == GIANT_TYPE.pattern


def _capella(make_star):
    """Capella's HIPPARCOS row merged with Gliese's row for Gl 194 A."""
    hip = make_star(
        "HIP 24608",
        42.199,
        79.1723,
        45.998,
        source="hipparcos",
        pos_source="hipparcos",
        hip=24608,
        sp="M1: comp",
        mag=0.08,
    )
    gliese = make_star(
        "Gl 194 A",
        41.2856,
        79.1705,
        45.9986,
        source="gliese",
        pos_source="gliese",
        sp="G5 III",
        mag=0.71,
    )
    return merge_catalogues([hip], [gliese])


def test_capella_takes_the_gliese_type_its_magnitude_allows(make_star):
    stars = _capella(make_star)
    fix_spectral_types(stars)
    assert [s["spectral_type"] for s in stars] == ["G5 III"]


def _placeholder_and_its_gaia_row(make_star):
    """HIP 23342, "O..." in HIPPARCOS, and its own Gaia row."""
    hip = make_star(
        "HIP 23342",
        136.0117,
        75.3161,
        -65.7678,
        source="hipparcos",
        pos_source="hipparcos",
        hip=23342,
        sp="O...",
        mag=11.98,
    )
    gaia = make_star(
        "Gaia DR3 4662265138153138688",
        134.1472,
        75.3161,
        -65.7678,
        source="gaia",
        pos_source="gaia",
        sp="M (est)",
        mag=11.95,
    )
    return merge_catalogues([hip], [gaia])


def test_placeholder_gives_way_to_the_gaia_estimate(make_star):
    stars = _placeholder_and_its_gaia_row(make_star)
    fix_spectral_types(stars)
    assert [s["spectral_type"] for s in stars] == ["M (est)"]


def test_first_type_that_fits_wins(make_star):
    """GJ 674: too faint for HIPPARCOS's K5, so Gliese's M3, not Gaia's."""
    hip = make_star(
        "HIP 85523",
        14.7964,
        262.1664,
        -46.8952,
        source="hipparcos",
        pos_source="hipparcos",
        hip=85523,
        sp="K5",
        mag=9.38,
    )
    gliese = make_star(
        "Gl 674",
        14.8,
        262.1664,
        -46.8952,
        source="gliese",
        pos_source="gliese",
        sp="M3",
        mag=9.38,
    )
    gaia = make_star(
        "Gaia DR3 5951824121022278144",
        14.8491,
        262.1664,
        -46.8952,
        source="gaia",
        pos_source="gaia",
        sp="M (est)",
        mag=9.38,
    )
    stars = merge_catalogues([hip], [gliese], [gaia])
    fix_spectral_types(stars)
    assert [s["spectral_type"] for s in stars] == ["M3"]


def test_type_no_catalogue_allows_is_cleared(make_star):
    """Gl 452 B, class F in Gliese, yet V 19.4 at 39.68 ly."""
    star = make_star(
        "Gl 452 B",
        39.6783,
        178.3204,
        -7.3753,
        source="gliese",
        sp="f",
        mag=19.4,
    )
    fix_spectral_types([star])
    assert star["spectral_type"] == ""


def test_entry_at_no_distance_is_left_for_the_validator(make_star):
    """A parallax of a million arcseconds rounds to 0.0 light-years."""
    star = make_star(
        "Gaia DR3 1", 0.0, 10.0, 10.0, source="gaia", sp="dM5", mag=12.0
    )

    fix_spectral_types([star])

    assert star["spectral_type"] == "M5"
    assert f"RANGE: 'Gaia DR3 1' distance 0.0 outside (0, {MAX_RADIUS_LY}]" in (
        validate_catalogue([star])
    )


def test_curated_type_is_left_for_the_validator(make_star):
    star = make_star("Gl 452 B", 39.6783, 178.3204, -7.3753, sp="F", mag=19.4)
    fix_spectral_types([star])
    assert star["spectral_type"] == "F"


def test_fixes_are_counted_by_kind(make_star):
    normalised = make_star(
        "Gl 251", 18.21, 103.7, 33.27, source="gliese", sp="dM4", mag=9.89
    )
    cleared = make_star(
        "Gl 452 B",
        39.6783,
        178.3204,
        -7.3753,
        source="gliese",
        sp="f",
        mag=19.4,
    )
    stars = [
        normalised,
        cleared,
        *_capella(make_star),
        *_placeholder_and_its_gaia_row(make_star),
    ]
    # The placeholder giving way to the Gaia estimate is normalised.
    assert fix_spectral_types(stars) == SpectralTypeFixes(
        normalised=2, replaced=1, trimmed=0, cleared=1
    )


@pytest.mark.parametrize(
    ("spectral_type", "expected"),
    [
        ("K5III", "K5"),
        ("K4III:", "K4"),
        ("G8III+...", "G8"),
        ("G0/G1III", "G0/G1"),
        ("G5 III", "G5"),
        ("F2mF5IIp", "F2mF5"),
        ("K5V", ""),
        ("K1IV", ""),
        ("M (est)", ""),
        ("III", ""),
    ],
)
def test_temperature_class_is_the_part_of_a_type_before_its_giant_class(
    spectral_type, expected
):
    assert temperature_class(spectral_type) == expected


def test_refused_giant_class_leaves_the_temperature_class(make_star):
    """HIP 112915, "K5III" in HIPPARCOS alone, at absolute V 6.08."""
    star = make_star(
        "HIP 112915",
        79.2218,
        343.0023,
        57.7169,
        source="hipparcos",
        hip=112915,
        sp="K5III",
        mag=8.01,
    )
    assert fix_spectral_types([star]) == SpectralTypeFixes(
        normalised=0, replaced=0, trimmed=1, cleared=0
    )
    assert star["spectral_type"] == "K5"


def test_another_catalogues_type_wins_over_a_temperature_class(make_star):
    hip = make_star(
        "HIP 1",
        48.69,
        82.1853,
        -65.4461,
        source="hipparcos",
        pos_source="hipparcos",
        hip=1,
        sp="K1III(p)",
        mag=6.88,
    )
    gaia = make_star(
        "Gaia DR3 1",
        48.69,
        82.1853,
        -65.4461,
        source="gaia",
        pos_source="gaia",
        sp="K (est)",
        mag=6.9,
    )
    stars = merge_catalogues([hip], [gaia])
    assert fix_spectral_types(stars) == SpectralTypeFixes(
        normalised=0, replaced=1, trimmed=0, cleared=0
    )
    assert [s["spectral_type"] for s in stars] == ["K (est)"]


def test_temperature_class_the_magnitude_rules_out_is_not_used(make_star):
    """An "M2III" at absolute V 5: too faint a giant, too bright a dwarf."""
    star = make_star(
        "HIP 2", 32.6156, 10.0, 10.0, source="hipparcos", sp="M2III", mag=5.0
    )
    fix_spectral_types([star])
    assert star["spectral_type"] == ""
