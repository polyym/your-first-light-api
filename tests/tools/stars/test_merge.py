"""Cross-catalogue matching and merging."""

import random

import pytest

from tools.updaters.stars.merge import (
    _pair_order,
    absorb,
    add_extra_stars,
    apply_overrides,
    dedup_by_coordinates,
    dedup_by_name,
    merge_catalogues,
    remove_beyond,
    same_star,
    share_system_distances,
)
from tools.updaters.stars.photometry import MISSING_MAGNITUDE
from tools.updaters.stars.write import write_stars


def test_same_distance_far_apart_on_sky_differs(make_star):
    a = make_star("Gaia DR3 1", 25.0, 10.0, 40.0, source="gaia")
    b = make_star("Gl 999", 25.0, 190.0, -40.0, source="gliese")
    assert not same_star(a, b)


def test_coarse_gliese_position_still_merges_in_window(make_star):
    """A Gliese position can be tens of arcseconds off even at J2000.

    The distance-checked window has to absorb that.
    """
    a = make_star(
        "Gaia DR3 1", 25.0, 100.0, 20.0, source="gaia", pos_source="gaia"
    )
    b = make_star(
        "Gl 999", 24.0, 100.0, 20.01, source="gliese", pos_source="gliese"
    )
    assert same_star(a, b)


def test_gliese_position_within_30_arcsec_merges(make_star):
    """Gl 734 A: 19 arcsec from its Gaia entry, 15% apart in distance."""
    a = make_star(
        "Gl 734 A", 52.5211, 280.0, 10.0, source="gliese", pos_source="gliese"
    )
    b = make_star(
        "Gaia DR3 4311983376654646656",
        61.0515,
        280.0,
        10.0053,
        source="gaia",
        pos_source="gaia",
        band="G",
    )
    assert same_star(a, b)


def test_precise_positions_20_arcsec_apart_do_not_merge(make_star):
    a = make_star(
        "HIP 1",
        60.0,
        280.0,
        10.0,
        source="hipparcos",
        pos_source="hipparcos",
        hip=1,
    )
    b = make_star(
        "Gaia DR3 2", 60.0, 280.0, 10.0056, source="gaia", pos_source="gaia"
    )
    assert not same_star(a, b)


def test_two_precise_positions_apart_are_two_stars(make_star):
    """Epsilon Indi A and its brown dwarf pair, 400 arcsec apart.

    At a common epoch HIPPARCOS and Gaia agree to well under an
    arcsecond for one star, so a Gaia entry this far from a HIPPARCOS
    star at the same distance is a wide companion.
    """
    a = make_star(
        "Epsilon Indi A",
        11.869,
        330.8402,
        -56.7860,
        source="hipparcos",
        pos_source="hipparcos",
        hip=108870,
    )
    b = make_star(
        "Gaia DR3 6412596012186366336",
        12.05,
        331.0441,
        -56.7828,
        source="gaia",
        pos_source="gaia",
        band="G",
    )
    assert not same_star(a, b)
    assert len(merge_catalogues([a], [b])) == 2


def test_different_hip_ids_never_merge(make_star):
    a = make_star(
        "61 Cygni A", 11.403, 316.7194, 38.7499, source="hipparcos", hip=104214
    )
    b = make_star(
        "61 Cygni B", 11.403, 316.7346, 38.7425, source="hipparcos", hip=104217
    )
    assert not same_star(a, b)


def test_same_hip_ids_merge_wherever_the_catalogues_put_them(make_star):
    a = make_star("HIP 100", 20.0, 10.0, 10.0, source="hipparcos", hip=100)
    b = make_star("Gl 5", 35.0, 200.0, -40.0, source="gliese", hip=100)
    assert same_star(a, b)


def test_distinct_common_names_never_merge(make_star):
    a = make_star("Kruger 60 A", 13.149, 336.9982, 57.6950)
    b = make_star("Kruger 60 B", 13.149, 336.9991, 57.6972)
    assert not same_star(a, b)


def test_same_common_name_merges(make_star):
    a = make_star(
        "Epsilon Eridani",
        10.475,
        53.2327,
        -9.4583,
        source="hipparcos",
        hip=16537,
    )
    b = make_star("Epsilon Eridani", 10.50, 53.2327, -9.4583, source="gliese")
    assert same_star(a, b)


def test_coincident_position_merges_despite_wild_distance(make_star):
    """Three arcseconds apart in two catalogues is one star.

    Gliese photometric parallaxes disagree with modern astrometry by up
    to 80% for faint distant stars, while chance alignments this close
    are vanishingly rare among the catalogue's stars.
    """
    a = make_star("NN 3050", 67.9492, 10.5, 20.0, source="gliese")
    b = make_star(
        "HIP 3533", 121.383, 10.5001, 20.0006, source="hipparcos", hip=3533
    )
    assert same_star(a, b)


def test_wide_window_still_requires_distance_agreement(make_star):
    """Beyond tier 1, rows unlike in brightness need distances that agree."""
    a = make_star("Gl 1", 60.0, 10.0, 20.0, source="gliese", mag=10.0)
    b = make_star("Gaia DR3 9", 90.0, 10.0, 20.05, source="gaia", mag=12.0)
    assert not same_star(a, b)


def _gl_633(make_star, **fields):
    """Gl 633 as the Gliese catalogue has it: 31 ly away, V 12.68."""
    fields = {"source": "gliese", "pos_source": "gliese", "mag": 12.68} | fields
    return make_star("Gl 633", 31.1813, 250.2055, -46.0053, **fields)


def _gl_633_in_gaia(make_star, **fields):
    """Its Gaia row: 55 ly away, V 12.69, 47 arcsec from the Gliese place."""
    fields = {"source": "gaia", "pos_source": "gaia", "mag": 12.69} | fields
    return make_star(
        "Gaia DR3 5942777301034031104", 55.3125, 250.1886, -45.9998, **fields
    )


def test_gliese_row_joins_the_row_of_like_brightness_nearby(make_star):
    """Neither the place nor the distance says Gl 633 is the Gaia star."""
    gliese = _gl_633(make_star)
    gaia = _gl_633_in_gaia(make_star)

    assert same_star(gliese, gaia)
    (merged,) = merge_catalogues([gliese], [gaia])
    assert merged["name"] == "Gl 633"
    assert merged["distance_ly"] == 55.3125
    assert (merged["ra_deg"], merged["dec_deg"]) == (250.1886, -45.9998)


@pytest.mark.parametrize(
    ("gliese_mag", "joined"), [(12.84, True), (12.94, False), (13.19, False)]
)
def test_rows_join_by_brightness_only_within_a_fifth_of_a_magnitude(
    make_star, gliese_mag, joined
):
    gliese = _gl_633(make_star, mag=gliese_mag)
    assert same_star(gliese, _gl_633_in_gaia(make_star)) is joined


@pytest.mark.parametrize(
    ("gliese_mag", "joined"),
    [(12.48, False), (12.49, True), (12.89, True), (12.9, False)],
)
def test_rows_a_fifth_of_a_magnitude_apart_join_whichever_is_brighter(
    make_star, gliese_mag, joined
):
    """In binary, 12.89 - 12.69 is over 0.2 and 12.69 - 12.49 under it."""
    gliese = _gl_633(make_star, mag=gliese_mag)
    assert same_star(gliese, _gl_633_in_gaia(make_star)) is joined


@pytest.mark.parametrize(("sep_arcsec", "joined"), [(170, True), (190, False)])
def test_rows_join_by_brightness_only_within_three_arcminutes(
    make_star, sep_arcsec, joined
):
    gliese = _gl_633(make_star)
    gaia = _gl_633_in_gaia(make_star)
    gaia["ra_deg"] = gliese["ra_deg"]
    gaia["dec_deg"] = gliese["dec_deg"] + sep_arcsec / 3600
    assert same_star(gliese, gaia) is joined


def test_like_brightness_never_joins_two_precise_positions(make_star):
    hipparcos = make_star(
        "HIP 1",
        31.1813,
        250.2055,
        -46.0053,
        source="hipparcos",
        pos_source="hipparcos",
        hip=1,
        mag=12.68,
    )
    assert not same_star(hipparcos, _gl_633_in_gaia(make_star))


def test_like_brightness_needs_two_v_magnitudes(make_star):
    gliese = _gl_633(make_star)
    assert not same_star(gliese, _gl_633_in_gaia(make_star, band="G"))
    gliese["apparent_magnitude"] = MISSING_MAGNITUDE
    assert not same_star(
        gliese, _gl_633_in_gaia(make_star, mag=MISSING_MAGNITUDE)
    )


def test_like_brightness_never_joins_two_rows_of_one_catalogue(make_star):
    """An equal binary one catalogue resolves stays two entries."""
    gliese = _gl_633(make_star)
    companion = make_star(
        "Gl 633 B",
        55.3125,
        250.1886,
        -45.9998,
        source="gliese",
        pos_source="gliese",
        mag=12.69,
    )
    assert not same_star(gliese, companion)
    assert len(merge_catalogues([gliese, companion])) == 2

    gaia = _gl_633_in_gaia(make_star)
    gaia_companion = _gl_633_in_gaia(make_star, mag=12.72)
    gaia_companion["name"] = "Gaia DR3 5942777301034031105"
    gaia_companion["dec_deg"] += 20 / 3600
    assert same_star(gliese, gaia) and same_star(gliese, gaia_companion)
    merged = merge_catalogues([gliese], [gaia, gaia_companion])
    assert [s["name"] for s in merged] == ["Gl 633", gaia_companion["name"]]
    assert merged[0]["distance_ly"] == gaia["distance_ly"]


def test_rows_of_one_catalogue_never_merge(make_star):
    """Gl 4 A and Gl 4 B: two components the catalogue resolved."""
    a = make_star("Gl 4 A", 37.5, 1.4219, 45.8115, source="gliese")
    b = make_star("Gl 4 B", 37.5, 1.4220, 45.8114, source="gliese")
    assert not same_star(a, b)
    assert len(merge_catalogues([a, b])) == 2


def test_duplicate_absorbed_across_catalogues(make_star):
    hip = [
        make_star(
            "Delta Pavonis",
            19.893,
            302.1830,
            -66.1819,
            source="hipparcos",
            hip=99240,
            sp="G8IV",
            mag=3.56,
        )
    ]
    gliese = [
        make_star(
            "Gl 780", 18.62, 302.1830, -66.1819, source="gliese", mag=3.56
        )
    ]
    merged = merge_catalogues(hip, gliese)
    assert len(merged) == 1
    assert merged[0]["name"] == "Delta Pavonis"


def test_binary_components_pair_with_closest(make_star):
    """Each Gaia component must join its own HIPPARCOS component.

    Absorbing into the first match instead would merge both Gaia
    entries into one star.
    """
    hip = [
        make_star(
            "61 Cygni A",
            11.403,
            316.7194,
            38.7499,
            source="hipparcos",
            hip=104214,
        ),
        make_star(
            "61 Cygni B",
            11.403,
            316.7346,
            38.7425,
            source="hipparcos",
            hip=104217,
        ),
    ]
    gaia = [
        make_star(
            "Gaia DR3 B", 11.40, 316.7351, 38.7426, source="gaia", band="G"
        ),
        make_star(
            "Gaia DR3 A", 11.41, 316.7199, 38.7500, source="gaia", band="G"
        ),
    ]
    merged = merge_catalogues(hip, gaia)
    assert len(merged) == 2
    assert {s["name"] for s in merged} == {"61 Cygni A", "61 Cygni B"}


def test_absorb_prefers_v_band_magnitude(make_star):
    gaia = [
        make_star(
            "Gaia DR3 X", 12.0, 50.0, 20.0, source="gaia", band="G", mag=8.2
        )
    ]
    gliese = [
        make_star(
            "Gl 123", 12.1, 50.0, 20.0, source="gliese", band="V", mag=9.1
        )
    ]
    merged = merge_catalogues(gaia, gliese)
    assert len(merged) == 1
    assert merged[0]["apparent_magnitude"] == 9.1
    assert merged[0]["magnitude_band"] == "V"


@pytest.mark.parametrize(
    ("band", "mag"), [("V", 15.2), ("G", 16.1)], ids=["gaia-v", "gaia-g"]
)
def test_missing_magnitude_takes_the_gaia_magnitude(make_star, band, mag):
    """A Gliese row without a V magnitude, and the Gaia row of its star."""
    gliese = [
        make_star(
            "Gl 9999 B",
            30.0,
            50.0,
            20.0,
            source="gliese",
            pos_source="gliese",
            mag=MISSING_MAGNITUDE,
        )
    ]
    gaia = [
        make_star(
            "Gaia DR3 1",
            30.2,
            50.0,
            20.0007,
            source="gaia",
            pos_source="gaia",
            band=band,
            mag=mag,
        )
    ]
    merged = merge_catalogues(gliese, gaia)
    assert [(s["apparent_magnitude"], s["magnitude_band"]) for s in merged] == [
        (mag, band)
    ]


def test_missing_magnitude_never_replaces_a_g_magnitude(make_star):
    """A row with no V magnitude leaves a Gaia G magnitude in place."""
    gaia = make_star(
        "Gaia DR3 1",
        30.2,
        50.0,
        20.0007,
        source="gaia",
        pos_source="gaia",
        band="G",
        mag=16.1,
    )
    gliese = make_star(
        "Gl 9999 B",
        30.0,
        50.0,
        20.0,
        source="gliese",
        pos_source="gliese",
        mag=MISSING_MAGNITUDE,
    )
    absorb(gaia, gliese)
    assert (gaia["apparent_magnitude"], gaia["magnitude_band"]) == (16.1, "G")


@pytest.mark.parametrize(
    ("mag", "expected"), [(14.9, True), (15.1, False)], ids=["4.9", "5.1"]
)
def test_rows_more_than_5_magnitudes_apart_are_two_stars(
    make_star, mag, expected
):
    a = make_star(
        "HIP 1",
        60.0,
        280.0,
        10.0,
        source="hipparcos",
        pos_source="hipparcos",
        hip=1,
        mag=10.0,
    )
    b = make_star(
        "Gaia DR3 2",
        60.0,
        280.0,
        10.001,
        source="gaia",
        pos_source="gaia",
        mag=mag,
    )
    assert same_star(a, b) is expected


def test_bright_star_keeps_its_place_beside_a_far_fainter_row(make_star):
    """Dubhe has no Gaia row of its own; a G 15.92 one is 13.6 arcsec off.

    Absorbing it would give Dubhe that row's distance and position.
    """
    hip = [
        make_star(
            "HIP 54061",
            123.6376,
            165.932,
            61.751,
            source="hipparcos",
            pos_source="hipparcos",
            hip=54061,
            mag=1.81,
        )
    ]
    gaia = [
        make_star(
            "Gaia DR3 862234033499968640",
            129.3105,
            165.9335,
            61.7473,
            source="gaia",
            pos_source="gaia",
            mag=16.41,
        )
    ]
    merged = merge_catalogues(hip, gaia)
    assert [(s["name"], s["distance_ly"]) for s in merged] == [
        ("HIP 54061", 123.6376),
        ("Gaia DR3 862234033499968640", 129.3105),
    ]


def test_absorbing_keeps_the_higher_planet_count_and_any_hip_number(
    make_star,
):
    existing = make_star("Gaia DR3 1", 20.0, 10.0, 10.0, source="gaia", exo=1)
    star = make_star(
        "HIP 100", 20.4, 10.0, 10.0, source="hipparcos", hip=100, exo=2
    )

    absorb(existing, star)

    assert existing["known_exoplanets"] == 2
    assert existing["_hip_id"] == 100
    assert existing["_merged_sources"] == {"gaia", "hipparcos"}
    assert (existing["name"], existing["distance_ly"]) == ("Gaia DR3 1", 20.0)


def test_absorbing_never_lowers_the_planet_count_or_changes_the_hip_number(
    make_star,
):
    existing = make_star(
        "HIP 100", 20.4, 10.0, 10.0, source="hipparcos", hip=100, exo=2
    )
    star = make_star("Gl 5", 21.0, 10.0, 10.0, source="gliese", hip=7, exo=1)

    absorb(existing, star)

    assert (existing["known_exoplanets"], existing["_hip_id"]) == (2, 100)


def test_absorbing_takes_a_common_name_over_a_designation(make_star):
    existing = make_star("HIP 100", 20.4, 10.0, 10.0, source="hipparcos")
    star = make_star("Vega", 21.0, 10.0, 10.0, source="gliese")

    absorb(existing, star)

    assert existing["name"] == "Vega"


def test_absorbing_fills_a_missing_position_from_a_lesser_catalogue(
    make_star,
):
    existing = make_star("Gaia DR3 1", 20.0, None, None, source="gaia")
    star = make_star(
        "Gl 5", 21.0, 10.0, -5.0, source="gliese", pos_source="gliese"
    )

    absorb(existing, star)

    assert {
        key: existing[key]
        for key in ("distance_ly", "ra_deg", "dec_deg", "_pos_source")
    } == {
        "distance_ly": 20.0,
        "ra_deg": 10.0,
        "dec_deg": -5.0,
        "_pos_source": "gliese",
    }


def test_adopted_distance_brings_its_position_and_sources(make_star):
    existing = make_star(
        "Gl 5", 21.0, 10.0, -5.0, source="gliese", pos_source="gliese"
    )
    star = make_star(
        "Gaia DR3 1", 20.0, 10.001, -5.001, source="gaia", pos_source="gaia"
    )

    absorb(existing, star)

    assert {
        key: existing[key]
        for key in (
            "distance_ly",
            "ra_deg",
            "dec_deg",
            "_pos_source",
            "_dist_source",
        )
    } == {
        "distance_ly": 20.0,
        "ra_deg": 10.001,
        "dec_deg": -5.001,
        "_pos_source": "gaia",
        "_dist_source": "gaia",
    }


def test_adopted_distance_is_then_as_reliable_as_its_catalogue(make_star):
    """A HIPPARCOS distance does not replace one adopted from Gaia."""
    existing = make_star("Gl 5", 21.0, 10.0, -5.0, source="gliese")
    absorb(existing, make_star("Gaia DR3 1", 20.0, 10.0, -5.0, source="gaia"))

    absorb(existing, make_star("HIP 100", 20.4, 10.0, -5.0, source="hipparcos"))

    assert existing["distance_ly"] == 20.0


def test_extra_star_replaces_the_entry_of_its_name_or_is_added(make_star):
    stars = [
        make_star("Sirius A", 8.7, 101.0, -16.0, source="hipparcos", hip=1),
        make_star("HIP 2", 20.0, 50.0, 50.0, source="hipparcos", hip=2),
    ]
    extras = [
        make_star("Sirius A", 8.6, 101.2872, -16.7161),
        make_star("Sirius B", 8.6, 101.2885, -16.7205),
    ]

    assert add_extra_stars(stars, extras) == (1, 1)
    assert stars == [extras[0], stars[1], extras[1]]
    assert stars[0] is not extras[0]


def test_designation_at_a_curated_stars_place_is_removed(make_star):
    curated = make_star("Sirius B", 8.6, 101.2885, -16.7205)
    stars = [
        make_star("HIP 2", 20.0, 50.0, 50.0, source="hipparcos"),
        make_star("Gaia DR3 9", 8.7, 101.2886, -16.7206, source="gaia"),
        make_star("Vega", 8.6, 101.2885, -16.7205, source="hipparcos"),
        curated,
    ]

    assert dedup_by_coordinates(stars, [curated]) == 1
    assert [s["name"] for s in stars] == ["HIP 2", "Vega", "Sirius B"]


def test_repeated_name_keeps_the_first_unless_only_the_second_has_a_hip(
    make_star,
):
    stars = [
        make_star("Vega", 25.0, 279.2, 38.8, source="gliese"),
        make_star("Altair", 16.7, 297.7, 8.9, source="hipparcos", hip=97649),
        make_star(
            "Vega", 25.04, 279.2347, 38.7837, source="hipparcos", hip=91262
        ),
        make_star("Altair", 16.8, 297.7, 8.9, source="gliese"),
        make_star("HIP 2", 20.0, 50.0, 50.0, source="hipparcos", hip=2),
    ]

    assert dedup_by_name(stars) == 2
    assert [(s["name"], s["distance_ly"]) for s in stars] == [
        ("Altair", 16.7),
        ("Vega", 25.04),
        ("HIP 2", 20.0),
    ]


def test_override_replaces_values_and_keeps_the_catalogue_position(make_star):
    stars = [
        make_star("HIP 2", 20.0, 50.0, 50.0, source="hipparcos", band="G"),
        make_star("Sirius A", 8.7, 101.0, -16.0, source="gaia", band="G"),
        make_star("Vega", 25.3, 279.0, 38.0, source="gaia", band="G"),
    ]

    assert apply_overrides(stars) == 2
    assert [
        (s["magnitude_band"], s.get("_catalogue_ra"), s.get("_catalogue_dec"))
        for s in stars
    ] == [("G", None, None), ("V", 101.0, -16.0), ("V", 279.0, 38.0)]


def test_merge_adopts_most_reliable_distance(make_star):
    hip = [
        make_star(
            "HIP 66267", 146.4553, 205.0, 30.0, source="hipparcos", hip=66267
        )
    ]
    gaia = [
        make_star(
            "Gaia DR3 1712527263348767488",
            128.4807,
            205.0,
            30.0,
            source="gaia",
            band="G",
        )
    ]
    merged = merge_catalogues(hip, gaia)
    assert len(merged) == 1
    assert merged[0]["distance_ly"] == 128.4807


def test_second_gaia_component_is_not_swallowed(make_star):
    """Once a merged entry holds one Gaia component, the other stays."""
    hip = [
        make_star(
            "HIP 66267", 146.4553, 205.0, 30.0, source="hipparcos", hip=66267
        )
    ]
    gaia = [
        make_star("Gaia DR3 A", 128.4807, 205.0, 30.0, source="gaia"),
        make_star("Gaia DR3 B", 127.9455, 205.0, 30.004, source="gaia"),
    ]
    assert len(merge_catalogues(hip, gaia)) == 2


def test_gaia_position_replaces_gliese_position(make_star):
    gliese = [
        make_star("Gl 451 A", 28.1169, 178.2441, 37.7196, source="gliese")
    ]
    gaia = [
        make_star(
            "Gaia DR3 4034171629042489088",
            29.9137,
            178.2449,
            37.7187,
            source="gaia",
            band="G",
        )
    ]
    merged = merge_catalogues(gliese, gaia)
    assert len(merged) == 1
    assert merged[0]["distance_ly"] == 29.9137
    assert merged[0]["ra_deg"] == 178.2449
    assert merged[0]["dec_deg"] == 37.7187


def test_hipparcos_position_survives_gliese_merge(make_star):
    hip = [
        make_star(
            "Delta Pavonis",
            19.893,
            302.1817,
            -66.1821,
            source="hipparcos",
            hip=99240,
        )
    ]
    gliese = [make_star("Gl 780", 18.62, 302.1830, -66.1819, source="gliese")]
    merged = merge_catalogues(hip, gliese)
    assert merged[0]["ra_deg"] == 302.1817
    assert merged[0]["dec_deg"] == -66.1821


@pytest.mark.parametrize("reverse", [False, True])
def test_bright_star_absorbs_its_own_gaia_row_in_any_order(make_star, reverse):
    """A companion 9 arcsec away must not take the bright row's place.

    Absorbing whichever Gaia row arrives first lists the bright star
    twice when the companion comes first: once as the HIPPARCOS entry
    holding the companion's data, once under its own Gaia designation.
    """
    hip = [
        make_star(
            "HIP 100",
            50.0,
            150.0,
            20.0,
            source="hipparcos",
            pos_source="hipparcos",
            hip=100,
            mag=5.0,
        )
    ]
    gaia = [
        make_star(
            "Gaia DR3 1",
            49.9,
            150.0,
            20.0025,
            source="gaia",
            pos_source="gaia",
            mag=9.0,
        ),
        make_star(
            "Gaia DR3 9",
            49.8,
            150.0001,
            20.0,
            source="gaia",
            pos_source="gaia",
            mag=5.02,
        ),
    ]
    if reverse:
        gaia.reverse()
    merged = merge_catalogues(hip, gaia)
    assert sorted(s["name"] for s in merged) == ["Gaia DR3 1", "HIP 100"]
    bright = next(s for s in merged if s["name"] == "HIP 100")
    assert bright["distance_ly"] == 49.8
    assert bright["ra_deg"] == 150.0001


@pytest.mark.parametrize("reverse", [False, True])
def test_tied_rows_pair_the_same_way_in_any_order(make_star, reverse):
    """Two Gaia rows at one rounded position, as a close pair can be."""
    hip = [make_star("HIP 100", 50.0, 150.0, 20.0, source="hipparcos", hip=100)]
    gaia = [
        make_star("Gaia DR3 1", 49.1, 150.0001, 20.0, source="gaia"),
        make_star("Gaia DR3 2", 49.2, 150.0001, 20.0, source="gaia"),
    ]
    if reverse:
        gaia.reverse()
    merged = merge_catalogues(hip, gaia)
    assert [(s["name"], s["distance_ly"]) for s in merged] == [
        ("HIP 100", 49.1),
        ("Gaia DR3 2", 49.2),
    ]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("second", "kept"),
    [
        ({"dist": 80.0, "mag": 12.6}, (37.7933, 12.6)),
        ({"dist": 37.7933, "mag": 13.1}, (37.7933, 12.6)),
    ],
)
def test_rows_sharing_a_designation_leave_the_same_entry_in_any_order(
    make_star, second, kept, reverse
):
    """The nearer of two such rows stays, then the brighter."""
    rows = [
        make_star("Gl 12", 37.7933, 3.9, 13.6, source="gliese", mag=12.6),
        make_star("Gl 12", second["dist"], 3.9, 13.6, source="gliese"),
    ]
    rows[1]["apparent_magnitude"] = second["mag"]
    for row in rows:
        row["_catalogue_id"] = "Gl 12"
    if reverse:
        rows.reverse()

    merged = merge_catalogues(rows)

    assert dedup_by_name(merged) == 1
    assert [(s["distance_ly"], s["apparent_magnitude"]) for s in merged] == [
        kept
    ]


def _crowded_field(make_star):
    """HIPPARCOS, Gliese and Gaia rows for one crowded square degree.

    Every HIPPARCOS star has its own Gaia row, many have a fainter Gaia
    companion within 15 arcsec and some a Gliese row with a coarse
    position, among unrelated Gaia stars. Some own rows have a twin at
    the same rounded position, as an unresolved close pair has, so
    their separations from the HIPPARCOS star tie exactly. Own rows,
    twins, companions and Gliese rows are close enough in magnitude to
    their HIPPARCOS star to be matched with it.
    """
    rng = random.Random(1)

    def near(ra, dec, arcsec):
        return (
            round(ra + rng.uniform(-arcsec, arcsec) / 3600, 4),
            round(dec + rng.uniform(-arcsec, arcsec) / 3600, 4),
        )

    hip, gliese, gaia = [], [], []
    for k in range(60):
        ra, dec = near(100.5, 20.5, 1800)
        dist = rng.uniform(5, 150)
        mag = round(rng.uniform(2, 9), 2)
        hip.append(
            make_star(
                f"HIP {k + 1}",
                dist,
                ra,
                dec,
                source="hipparcos",
                pos_source="hipparcos",
                hip=k + 1,
                mag=mag,
            )
        )
        own = near(ra, dec, 0.5)
        gaia.append(
            make_star(
                f"Gaia DR3 {1000 + k}",
                round(dist * rng.uniform(0.97, 1.03), 4),
                *own,
                source="gaia",
                pos_source="gaia",
                mag=mag,
            )
        )
        if rng.random() < 0.25:
            gaia.append(
                make_star(
                    f"Gaia DR3 {4000 + k}",
                    round(dist * rng.uniform(0.97, 1.03), 4),
                    *own,
                    source="gaia",
                    pos_source="gaia",
                    mag=mag + 1,
                )
            )
        if rng.random() < 0.5:
            gaia.append(
                make_star(
                    f"Gaia DR3 {2000 + k}",
                    round(dist * rng.uniform(0.97, 1.03), 4),
                    *near(ra, dec, 10),
                    source="gaia",
                    pos_source="gaia",
                    mag=mag + 4,
                )
            )
        if rng.random() < 0.5:
            gliese.append(
                make_star(
                    f"Gl {k + 1}",
                    round(dist * rng.uniform(0.85, 1.15), 4),
                    *near(ra, dec, 25),
                    source="gliese",
                    pos_source="gliese",
                    mag=mag,
                )
            )
    for k in range(200):
        gaia.append(
            make_star(
                f"Gaia DR3 {3000 + k}",
                round(rng.uniform(5, 150), 4),
                *near(100.5, 20.5, 1800),
                source="gaia",
                pos_source="gaia",
                mag=15.0,
            )
        )
    return hip, gliese, gaia


def test_shuffled_catalogues_merge_to_the_same_catalogue(make_star, tmp_path):
    """Upstream services do not promise a row order; nor may the merge."""
    catalogues = _crowded_field(make_star)

    def written(catalogues, path):
        stars = merge_catalogues(*catalogues)
        dedup_by_name(stars)
        write_stars(stars, path)
        return path.read_bytes()

    expected = written(catalogues, tmp_path / "given.json")
    rng = random.Random(2)
    for n in range(5):
        shuffled = [rng.sample(rows, len(rows)) for rows in catalogues]
        assert written(shuffled, tmp_path / f"{n}.json") == expected


def test_merged_entry_keeps_the_gaia_source_of_its_gaia_row(make_star):
    """The Exoplanet Archive names most faint hosts by Gaia source alone."""
    gliese = make_star("NN 3053", 48.9, 11.2469, -15.2713, source="gliese")
    gaia = make_star(
        "Gaia DR3 2371032916186181760",
        48.8047,
        11.2469,
        -15.2713,
        source="gaia",
        pos_source="gaia",
    )
    gaia["_gaia_id"] = "2371032916186181760"

    (merged,) = merge_catalogues([gliese], [gaia])

    assert merged["name"] == "NN 3053"
    assert merged["_gaia_id"] == "2371032916186181760"


def _with(star, **keys):
    """An entry with merge bookkeeping keys added, such as _gaia_id."""
    return star | {f"_{key}": value for key, value in keys.items()}


def test_same_gaia_ids_merge_and_different_ones_never(make_star):
    """A HIPPARCOS star joins only the Gaia row Gaia DR3 matched to it."""
    hip = _with(
        make_star(
            "HIP 1",
            50.0,
            10.0,
            10.0,
            source="hipparcos",
            pos_source="hipparcos",
        ),
        hip_id=1,
        gaia_id="11",
    )
    own = _with(
        make_star("Gaia DR3 11", 45.0, 10.0, 10.003, source="gaia"),
        pos_source="gaia",
        gaia_id="11",
    )
    other = _with(
        make_star("Gaia DR3 12", 50.0, 10.0, 10.0, source="gaia"),
        pos_source="gaia",
        gaia_id="12",
    )
    # 10.8 arcsec apart, 10 per cent apart in distance.
    assert same_star(hip, own)
    # At the same place and distance.
    assert not same_star(hip, other)


def test_a_shared_gaia_id_joins_before_a_gliese_row_of_like_brightness(
    make_star,
):
    """A Gliese component 2 arcsec from the Gaia row, within 0.05 mag.

    Among like pairs at Gliese range it would join first and leave the
    HIPPARCOS star, 8 arcsec away, without the Gaia row matched to it.
    """
    arcsec = 1 / 3600
    hip = _with(
        make_star(
            "HIP 1",
            47.0,
            10.0,
            10.0,
            source="hipparcos",
            pos_source="hipparcos",
            mag=10.5,
        ),
        hip_id=1,
        gaia_id="11",
    )
    gliese = [
        make_star(
            "Gl 1 A",
            47.0,
            10.0,
            10.0,
            source="gliese",
            pos_source="gliese",
            mag=10.5,
        ),
        make_star(
            "Gl 1 B",
            47.0,
            10.0,
            10.0 + 10 * arcsec,
            source="gliese",
            pos_source="gliese",
            mag=10.2,
        ),
    ]
    gaia = _with(
        make_star(
            "Gaia DR3 11",
            44.3,
            10.0,
            10.0 + 8 * arcsec,
            source="gaia",
            mag=10.25,
        ),
        pos_source="gaia",
        gaia_id="11",
    )

    merged = {s["name"]: s for s in merge_catalogues([hip], gliese, [gaia])}

    assert set(merged) == {"HIP 1", "Gl 1 B"}
    assert merged["HIP 1"]["distance_ly"] == 44.3
    assert "_gaia_id" not in merged["Gl 1 B"]


def test_gliese_rows_join_the_gaia_rows_of_like_brightness_first(make_star):
    """NN 4288 A and B: B lies nearer A's Gaia row than A does.

    Nearest first, B would take A's row and A would take B's.
    """
    arcsec = 1 / 3600
    gliese = [
        make_star(
            "NN 1 A",
            40.0,
            10.0,
            10.0,
            source="gliese",
            pos_source="gliese",
            mag=12.0,
        ),
        make_star(
            "NN 1 B",
            40.0,
            10.0,
            10.0 + 10 * arcsec,
            source="gliese",
            pos_source="gliese",
            mag=13.5,
        ),
    ]
    gaia = [
        make_star(
            "Gaia DR3 A",
            38.65,
            10.0,
            10.0 + 25 * arcsec,
            source="gaia",
            pos_source="gaia",
            mag=12.0,
        ),
        make_star(
            "Gaia DR3 B",
            41.0,
            10.0,
            10.0 - 16 * arcsec,
            source="gaia",
            pos_source="gaia",
            mag=13.5,
        ),
    ]

    merged = {s["name"]: s for s in merge_catalogues(gliese, gaia)}

    assert set(merged) == {"NN 1 A", "NN 1 B"}
    assert merged["NN 1 A"]["distance_ly"] == 38.65
    assert merged["NN 1 B"]["distance_ly"] == 41.0


def test_absorbing_keeps_the_gliese_system(make_star):
    hip = make_star("HIP 61941", 39.2, 190.4152, -1.4494, source="hipparcos")
    gliese = _with(
        make_star("Gl 482 A", 33.05, 190.4152, -1.4494, source="gliese"),
        gliese_system="Gl 482",
    )
    absorb(hip, gliese)
    assert hip["_gliese_system"] == "Gl 482"


def test_gliese_component_takes_its_system_s_measured_distance(make_star):
    """Gl 853 B, 39.6 ly by its Gliese parallax; Gl 853 A, 45.9 by Gaia."""
    primary = _with(
        make_star(
            "HIP 110109", 45.8768, 334.5651, -53.6271, source="hipparcos"
        ),
        dist_source="gaia",
        merged_sources={"hipparcos", "gliese", "gaia"},
        gliese_system="Gl 853",
    )
    component = _with(
        make_star("Gl 853 B", 39.582, 334.5665, -53.6267, source="gliese"),
        gliese_system="Gl 853",
    )
    stars = [primary, component]

    assert share_system_distances(stars) == 1

    assert component["distance_ly"] == 45.8768
    assert component["_dist_source"] == "gaia"


def test_only_a_measured_component_gives_its_distance(make_star):
    """Two components known only from the Gliese catalogue keep theirs."""
    stars = [
        _with(
            make_star(f"Gl 9 {c}", dist, 10.0, 10.0, source="gliese"),
            gliese_system="Gl 9",
        )
        for c, dist in (("A", 20.0), ("B", 22.0))
    ]
    assert share_system_distances(stars) == 0
    assert [s["distance_ly"] for s in stars] == [20.0, 22.0]


def test_nearest_measured_component_gives_the_distance(make_star):
    stars = [
        _with(
            make_star(f"HIP {n}", dist, 10.0, dec, source="hipparcos"),
            gliese_system="Gl 9",
        )
        for n, dist, dec in ((1, 30.0, 10.0), (2, 31.0, 10.5))
    ] + [
        _with(
            make_star("Gl 9 C", 25.0, 10.0, 10.4, source="gliese"),
            gliese_system="Gl 9",
        )
    ]
    share_system_distances(stars)
    assert stars[2]["distance_ly"] == 31.0


def test_entries_beyond_the_radius_are_removed(make_star):
    stars = [
        make_star("HIP 1", 160.0, 10.0, 10.0),
        make_star("HIP 2", 160.01, 20.0, 10.0),
    ]
    assert remove_beyond(stars, 160) == 1
    assert [s["name"] for s in stars] == ["HIP 1"]


@pytest.mark.parametrize(
    ("row_mag", "sep_arcsec", "first"),
    [
        (12.5, 29.0, True),
        (12.51, 29.0, False),
        (12.0, 29.9, True),
        (12.0, 30.0, False),
    ],
    ids=["0.5-mag", "0.51-mag", "29.9-arcsec", "30-arcsec"],
)
def test_like_pair_at_gliese_range_joins_before_the_rest(
    make_star, row_mag, sep_arcsec, first
):
    gliese = make_star(
        "NN 1", 40.0, 10.0, 10.0, source="gliese", pos_source="gliese", mag=12.0
    )
    gaia = make_star(
        "Gaia DR3 1",
        40.0,
        10.0,
        10.0 + sep_arcsec / 3600,
        source="gaia",
        pos_source="gaia",
        mag=row_mag,
    )
    tier, _sep = _pair_order(gliese, gaia, sep_arcsec / 3600)
    assert tier == (1 if first else 2)


def test_like_pair_of_two_precise_positions_waits_its_turn(make_star):
    """HIPPARCOS and Gaia positions agree to well under an arcsecond."""
    hip = make_star(
        "HIP 1", 40.0, 10.0, 10.0, source="hipparcos", pos_source="hipparcos"
    )
    gaia = make_star(
        "Gaia DR3 1", 40.0, 10.0, 10.0, source="gaia", pos_source="gaia"
    )
    assert _pair_order(hip, gaia, 9 / 3600)[0] == 2


@pytest.mark.parametrize("key", ["hip_id", "gaia_id"])
def test_pair_sharing_an_id_joins_first(make_star, key):
    entry = _with(make_star("HIP 1", 40.0, 10.0, 10.0), **{key: 7})
    row = _with(make_star("Gaia DR3 7", 40.0, 10.0, 10.1), **{key: 7})
    assert _pair_order(entry, row, 0.1) == (0, 0.1)
