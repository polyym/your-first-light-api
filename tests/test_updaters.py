"""Offline unit tests for the data updater tools.

These exercise the merge, validation, and write logic with
synthetic data; no network access is required.
"""

import json
import math

import numpy as np

import tools.update_data as update_data
import tools.updaters.update_eclipses as update_eclipses
import tools.updaters.update_stars as update_stars
from tools.updaters.update_stars import (
    _same_star,
    find_positional_duplicates,
    gaia_g_to_v,
    merge_catalogues,
    validate_catalogue,
)


def _star(
    name,
    dist,
    ra,
    dec,
    source=None,
    hip=None,
    band="V",
    sp="M0V",
    mag=10.0,
    exo=0,
):
    s = {
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
        s["_source"] = source
    if hip:
        s["_hip_id"] = hip
    return s


class TestSameStar:
    """The duplicate heuristic that caused finding 2."""

    def test_parallax_disagreement_at_20_ly_merges(self):
        """The Delta Pavonis case: same position, distances
        1.27 ly apart. The old fixed 1.0 ly tolerance called
        these two different stars."""
        a = _star(
            "Delta Pavonis", 19.893, 302.1830, -66.1819,
            source="hipparcos", hip=99240,
        )
        b = _star(
            "Gl 780", 18.62, 302.1830, -66.1819,
            source="gliese",
        )
        assert _same_star(a, b)

    def test_same_distance_far_apart_on_sky_differs(self):
        a = _star("Gaia DR3 1", 25.0, 10.0, 40.0, source="gaia")
        b = _star("Gl 999", 25.0, 190.0, -40.0, source="gliese")
        assert not _same_star(a, b)

    def test_same_source_never_merges(self):
        """Two rows in one catalogue are two objects, e.g. a
        resolved binary in Gaia."""
        a = _star(
            "Gaia DR3 1", 10.0, 100.0, 10.0, source="gaia",
        )
        b = _star(
            "Gaia DR3 2", 10.0, 100.001, 10.001, source="gaia",
        )
        assert not _same_star(a, b)

    def test_coarse_gliese_position_still_merges_in_window(self):
        """A Gliese position can be tens of arcseconds off even
        after propagation to J2000; the distance-checked window
        must absorb that."""
        a = _star(
            "Gaia DR3 1", 25.0, 100.0, 20.0, source="gaia",
        )
        a["_pos_source"] = "gaia"
        b = _star("Gl 999", 24.0, 100.0, 20.01, source="gliese")
        b["_pos_source"] = "gliese"
        assert _same_star(a, b)

    def test_gliese_position_within_30_arcsec_merges(self):
        """Gl 734 A sits 19 arcsec from its Gaia entry with a 15%
        photometric-distance disagreement: same star."""
        a = _star("Gl 734 A", 52.5211, 280.0, 10.0, source="gliese")
        a["_pos_source"] = "gliese"
        b = _star(
            "Gaia DR3 4311983376654646656", 61.0515,
            280.0, 10.0053, source="gaia", band="G",
        )
        b["_pos_source"] = "gaia"
        assert _same_star(a, b)

    def test_precise_positions_20_arcsec_apart_do_not_merge(self):
        a = _star(
            "HIP 1", 60.0, 280.0, 10.0, source="hipparcos", hip=1,
        )
        a["_pos_source"] = "hipparcos"
        b = _star(
            "Gaia DR3 2", 60.0, 280.0, 10.0056, source="gaia",
        )
        b["_pos_source"] = "gaia"
        assert not _same_star(a, b)

    def test_two_precise_positions_apart_are_two_stars(self):
        """Every source is at epoch J2000, so HIPPARCOS and Gaia
        agree to well under an arcsecond for the same star. A
        Gaia entry 400 arcsec from a HIPPARCOS star at the same
        distance is a wide companion (Epsilon Indi A and its
        brown-dwarf pair), not the star itself."""
        a = _star(
            "Epsilon Indi A", 11.869, 330.8402, -56.7860,
            source="hipparcos", hip=108870,
        )
        a["_pos_source"] = "hipparcos"
        b = _star(
            "Gaia DR3 6412596012186366336", 12.05,
            331.0441, -56.7828, source="gaia", band="G",
        )
        b["_pos_source"] = "gaia"
        assert not _same_star(a, b)
        assert len(merge_catalogues([a], [b])) == 2

    def test_different_hip_ids_never_merge(self):
        a = _star(
            "61 Cygni A", 11.403, 316.7194, 38.7499,
            source="hipparcos", hip=104214,
        )
        b = _star(
            "61 Cygni B", 11.403, 316.7346, 38.7425,
            source="hipparcos", hip=104217,
        )
        assert not _same_star(a, b)

    def test_distinct_common_names_never_merge(self):
        a = _star("Kruger 60 A", 13.149, 336.9982, 57.6950)
        b = _star("Kruger 60 B", 13.149, 336.9991, 57.6972)
        assert not _same_star(a, b)

    def test_same_common_name_merges(self):
        a = _star(
            "Epsilon Eridani", 10.475, 53.2327, -9.4583,
            source="hipparcos", hip=16537,
        )
        b = _star(
            "Epsilon Eridani", 10.50, 53.2327, -9.4583,
            source="gliese",
        )
        assert _same_star(a, b)

    def test_coincident_position_merges_despite_wild_distance(
        self,
    ):
        """Gliese photometric parallaxes disagree with modern
        astrometry by up to ~80% for faint distant stars, but
        at ~3 arcsec a cross-catalogue pair is the same star:
        chance alignments this close are essentially impossible
        with 26k stars on the whole sky."""
        a = _star(
            "NN 3050", 67.9492, 10.5, 20.0, source="gliese",
        )
        b = _star(
            "HIP 3533", 121.383, 10.5001, 20.0006,
            source="hipparcos", hip=3533,
        )
        assert _same_star(a, b)

    def test_pm_window_still_requires_distance_agreement(self):
        """Beyond the coincident tier, the wide proper-motion
        window must not swallow unrelated stars."""
        a = _star(
            "Gl 1", 60.0, 10.0, 20.0, source="gliese",
        )
        b = _star(
            "Gaia DR3 9", 90.0, 10.0, 20.05, source="gaia",
        )
        assert not _same_star(a, b)


class TestMergeCatalogues:
    """Cross-catalogue merging with best-match selection."""

    def test_duplicate_absorbed_across_catalogues(self):
        hip = [_star(
            "Delta Pavonis", 19.893, 302.1830, -66.1819,
            source="hipparcos", hip=99240, sp="G8IV", mag=3.56,
        )]
        gliese = [_star(
            "Gl 780", 18.62, 302.1830, -66.1819,
            source="gliese",
        )]
        merged = merge_catalogues(hip, gliese)
        assert len(merged) == 1
        assert merged[0]["name"] == "Delta Pavonis"

    def test_binary_components_pair_with_closest(self):
        """When both components exist in both catalogues, each
        Gaia entry must be absorbed by ITS component, not the
        first one that matches."""
        hip = [
            _star(
                "61 Cygni A", 11.403, 316.7194, 38.7499,
                source="hipparcos", hip=104214,
            ),
            _star(
                "61 Cygni B", 11.403, 316.7346, 38.7425,
                source="hipparcos", hip=104217,
            ),
        ]
        gaia = [
            _star(
                "Gaia DR3 B", 11.40, 316.7351, 38.7426,
                source="gaia", band="G",
            ),
            _star(
                "Gaia DR3 A", 11.41, 316.7199, 38.7500,
                source="gaia", band="G",
            ),
        ]
        merged = merge_catalogues(hip, gaia)
        assert len(merged) == 2
        names = {s["name"] for s in merged}
        assert names == {"61 Cygni A", "61 Cygni B"}

    def test_absorb_prefers_v_band_magnitude(self):
        gaia = [_star(
            "Gaia DR3 X", 12.0, 50.0, 20.0,
            source="gaia", band="G", mag=8.2,
        )]
        gliese = [_star(
            "Gl 123", 12.1, 50.0, 20.0,
            source="gliese", band="V", mag=9.1,
        )]
        merged = merge_catalogues(gaia, gliese)
        assert len(merged) == 1
        assert merged[0]["apparent_magnitude"] == 9.1
        assert merged[0]["magnitude_band"] == "V"

    def test_real_binary_survives_merge(self):
        """Two same-source rows at one position and distance
        stay two stars."""
        gaia = [
            _star(
                "Gaia DR3 1", 15.0, 200.0, -30.0,
                source="gaia",
            ),
            _star(
                "Gaia DR3 2", 15.01, 200.001, -30.001,
                source="gaia",
            ),
        ]
        merged = merge_catalogues(gaia)
        assert len(merged) == 2

    def test_merge_adopts_most_reliable_distance(self):
        """When HIPPARCOS and Gaia disagree about a star's
        distance, the merged entry keeps the Gaia value."""
        hip = [_star(
            "HIP 66267", 146.4553, 205.0, 30.0,
            source="hipparcos", hip=66267,
        )]
        gaia = [_star(
            "Gaia DR3 1712527263348767488", 128.4807,
            205.0, 30.0, source="gaia", band="G",
        )]
        merged = merge_catalogues(hip, gaia)
        assert len(merged) == 1
        assert merged[0]["distance_ly"] == 128.4807

    def test_second_gaia_component_is_not_swallowed(self):
        """After a merged entry absorbs one Gaia component, the
        other Gaia component of the pair must stay separate."""
        hip = [_star(
            "HIP 66267", 146.4553, 205.0, 30.0,
            source="hipparcos", hip=66267,
        )]
        gaia = [
            _star(
                "Gaia DR3 A", 128.4807, 205.0, 30.0,
                source="gaia",
            ),
            _star(
                "Gaia DR3 B", 127.9455, 205.0, 30.004,
                source="gaia",
            ),
        ]
        merged = merge_catalogues(hip, gaia)
        assert len(merged) == 2


class TestPositionalDuplicates:
    """The validation net that finding 2 showed was missing."""

    def test_detects_disagreeing_distance_duplicate(self):
        stars = [
            _star("Delta Pavonis", 19.893, 302.1830, -66.1819),
            _star("Gl 780", 18.62, 302.1831, -66.1820),
            _star("Vega", 25.04, 279.2347, 38.7837),
        ]
        pairs = find_positional_duplicates(stars)
        assert len(pairs) == 1
        i, j, _sep = pairs[0]
        assert {stars[i]["name"], stars[j]["name"]} == {
            "Delta Pavonis", "Gl 780",
        }

    def test_multiple_system_components_are_exempt(self):
        """Same position and same distance is a real system
        (Sirius A/B, Luhman 16AB), not a duplicate."""
        stars = [
            _star("Sirius A", 8.6094, 101.2872, -16.7161),
            _star("Sirius B", 8.6094, 101.2872, -16.7161),
        ]
        assert find_positional_duplicates(stars) == []

    def test_same_source_resolved_double_is_exempt(self):
        """A double resolved within ONE catalogue whose noisy
        parallaxes disagree (e.g. HIP 34085/34087) is two real
        stars, not a duplicate."""
        stars = [
            _star(
                "HIP 34085", 121.2927, 104.0, -25.0,
                source="hipparcos", hip=34085,
            ),
            _star(
                "HIP 34087", 110.4864, 104.0, -25.0036,
                source="hipparcos", hip=34087,
            ),
        ]
        assert find_positional_duplicates(stars) == []

    def test_written_source_field_is_recognised(self):
        """The final catalogue carries 'source' (not '_source');
        the exemption must work on written data too."""
        a = _star("HIP 34085", 121.2927, 104.0, -25.0)
        b = _star("HIP 34087", 110.4864, 104.0, -25.0036)
        a["source"] = "hipparcos"
        b["source"] = "hipparcos"
        assert find_positional_duplicates([a, b]) == []

    def test_written_sources_list_is_recognised(self):
        """A component pair that shares any contributing
        catalogue (recorded in the written 'sources' list) is a
        real pair with discordant parallaxes, not a duplicate."""
        a = _star("HIP 79242", 111.7007, 242.5626, -84.2316)
        b = _star("Gl 606.1", 83.6297, 242.569, -84.2315)
        a["sources"] = ["gaia", "gliese", "hipparcos"]
        b["sources"] = ["gliese"]
        assert find_positional_duplicates([a, b]) == []

    def test_disjoint_sources_are_still_flagged(self):
        a = _star("HIP 1", 111.7, 242.5626, -84.2316)
        b = _star("Gl 2", 83.6, 242.569, -84.2315)
        a["sources"] = ["hipparcos"]
        b["sources"] = ["gliese"]
        assert len(find_positional_duplicates([a, b])) == 1

    def test_validate_catalogue_fails_on_positional_dup(self):
        stars = [
            _star("Delta Pavonis", 19.893, 302.1830, -66.1819),
            _star("Gl 780", 18.62, 302.1831, -66.1820),
        ]
        errors = [
            e for e in validate_catalogue(stars)
            if e.startswith("POSITIONAL_DUP")
        ]
        assert len(errors) == 1
        assert "Gl 780" in errors[0]


class TestCatalogueData:
    """Integrity of the shipped data/stars.json."""

    def test_no_positional_duplicates_in_catalogue(self):
        """Fails on the v1.0 catalogue (~4,000 duplicated
        stars); guards every regenerated catalogue after it."""
        from src.compute import NEARBY_STARS

        pairs = find_positional_duplicates(NEARBY_STARS)
        sample = [
            (NEARBY_STARS[i]["name"], NEARBY_STARS[j]["name"])
            for i, j, _ in pairs[:5]
        ]
        assert not pairs, (
            f"{len(pairs)} positional duplicates, e.g. {sample}"
        )


class TestFetchGuards:
    """A degraded upstream fetch must fail the run loudly."""

    def test_healthy_counts_pass(self):
        assert update_stars.check_fetch_counts({
            "hipparcos": 6497,
            "gliese": 3148,
            "gaia": 48418,
        }) == []
        assert update_stars.check_fetch_counts({
            "exoplanet_archive": 5643,
        }) == []

    def test_thin_source_is_rejected(self):
        errors = update_stars.check_fetch_counts({
            "hipparcos": 6497,
            "gliese": 3148,
            "gaia": 512,
        })
        assert len(errors) == 1
        assert "gaia" in errors[0]
        assert "512" in errors[0]

    def test_failed_source_is_rejected(self):
        """A fetcher that errored returns an empty list; that
        must never silently produce a partial catalogue."""
        errors = update_stars.check_fetch_counts({
            "hipparcos": 0,
            "gliese": 0,
            "gaia": 0,
        })
        assert len(errors) == 3

    def test_thin_exoplanet_archive_is_rejected(self):
        errors = update_stars.check_fetch_counts({
            "exoplanet_archive": 0,
        })
        assert len(errors) == 1
        assert "exoplanet_archive" in errors[0]


class TestEclipseYearCoverage:
    """Losing one century page must fail eclipse validation."""

    @staticmethod
    def _shipped_dates():
        import json
        from datetime import date
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent
            / "data" / "eclipses.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        solar = [
            date.fromisoformat(d) for d in data["solarEclipses"]
        ]
        lunar = [
            date.fromisoformat(d) for d in data["lunarEclipses"]
        ]
        return solar, lunar

    def test_shipped_catalogue_validates(self):
        solar, lunar = self._shipped_dates()
        assert update_eclipses.validate(solar, lunar) == []

    def test_missing_1900_lunar_page_fails(self):
        """Dropping 1900's lunar eclipses barely moves the
        totals but must still fail per-year coverage."""
        solar, lunar = self._shipped_dates()
        lunar = [d for d in lunar if d.year != 1900]
        errors = update_eclipses.validate(solar, lunar)
        assert any(
            "1900" in e and "lunar" in e for e in errors
        )

    def test_missing_1900_solar_page_fails(self):
        solar, lunar = self._shipped_dates()
        solar = [d for d in solar if d.year != 1900]
        errors = update_eclipses.validate(solar, lunar)
        assert any(
            "1900" in e and "solar" in e for e in errors
        )


class TestSpectralEstimates:
    """Coarse spectral classes from Gaia BP-RP colour."""

    def test_solar_colour_is_g(self):
        est = update_stars.estimate_spectral_class(
            0.82, 4.8, 32.6,
        )
        assert est == "G (est)"

    def test_red_dwarf_colour_is_m(self):
        est = update_stars.estimate_spectral_class(
            3.1, 14.0, 30.0,
        )
        assert est == "M (est)"

    def test_faint_blue_object_is_white_dwarf(self):
        # Sirius B-like: blue but ~11 mag at 8.6 ly.
        est = update_stars.estimate_spectral_class(
            -0.1, 8.5, 8.6,
        )
        assert est == "D (est)"

    def test_missing_colour_gives_no_estimate(self):
        assert update_stars.estimate_spectral_class(
            None, 10.0, 30.0,
        ) == ""
        assert update_stars.estimate_spectral_class(
            6.0, 10.0, 30.0,
        ) == ""

    def test_estimates_group_in_api_breakdown(self):
        from src.compute import classify_spectral

        assert classify_spectral("M (est)") == "Red dwarf (M)"
        assert classify_spectral("D (est)") == "White dwarf (D)"


class TestGaiaGToV:
    """Gaia G to Johnson V conversion (finding 20)."""

    def test_red_star_v_is_fainter_than_g(self):
        v = gaia_g_to_v(10.0, 3.0)
        assert v is not None
        assert v > 11.0

    def test_solar_colour_close_to_g(self):
        v = gaia_g_to_v(10.0, 0.82)
        assert v is not None
        assert abs(v - 10.0) < 0.3

    def test_out_of_range_colour_returns_none(self):
        assert gaia_g_to_v(10.0, 5.5) is None
        assert gaia_g_to_v(10.0, None) is None


class TestAtomicWrites:
    """Interrupted or repeated runs cannot corrupt data files."""

    def test_write_stars_unchanged_returns_false(self, tmp_path):
        out = tmp_path / "stars.json"
        stars = [_star("Vega", 25.04, 279.2347, 38.7837)]
        assert update_stars.write_stars(list(stars), out) is True
        assert update_stars.write_stars(list(stars), out) is False
        # No temp file left behind either way.
        assert list(tmp_path.glob("*.tmp")) == []

    def test_write_stars_change_is_detected(self, tmp_path):
        out = tmp_path / "stars.json"
        update_stars.write_stars(
            [_star("Vega", 25.04, 279.2347, 38.7837)], out,
        )
        changed = update_stars.write_stars(
            [_star("Vega", 25.04, 279.2347, 38.7837, exo=1)],
            out,
        )
        assert changed is True
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data[0]["known_exoplanets"] == 1

    def test_write_eclipses_unchanged_keeps_generated_stamp(
        self, tmp_path,
    ):
        from datetime import date

        out = tmp_path / "eclipses.json"
        solar = [date(2024, 4, 8)]
        lunar = [date(2022, 11, 8)]
        assert update_eclipses.write_eclipses(
            solar, lunar, out,
        ) is True

        # Backdate the generated stamp, rerun with identical
        # data: file must not be rewritten.
        data = json.loads(out.read_text(encoding="utf-8"))
        data["generated"] = "2001-01-01"
        out.write_text(json.dumps(data), encoding="utf-8")
        assert update_eclipses.write_eclipses(
            solar, lunar, out,
        ) is False
        after = json.loads(out.read_text(encoding="utf-8"))
        assert after["generated"] == "2001-01-01"
        assert list(tmp_path.glob("*.tmp")) == []


class TestManifest:
    """data/manifest.json bookkeeping in update_data.py."""

    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(update_data, "_DATA_DIR", tmp_path)
        monkeypatch.setattr(
            update_data,
            "_MANIFEST_PATH",
            tmp_path / "manifest.json",
        )
        (tmp_path / "stars.json").write_text(
            json.dumps([{"name": "Vega"}, {"name": "Sirius A"}]),
            encoding="utf-8",
        )
        (tmp_path / "eclipses.json").write_text(
            json.dumps({
                "solarEclipses": ["2024-04-08"],
                "lunarEclipses": ["2022-11-08"],
            }),
            encoding="utf-8",
        )

    def test_manifest_created_with_counts(
        self, tmp_path, monkeypatch,
    ):
        self._setup(tmp_path, monkeypatch)
        changed = update_data.update_manifest({
            "stars.json": True,
            "eclipses.json": True,
        })
        assert changed is True
        m = json.loads(
            (tmp_path / "manifest.json").read_text(
                encoding="utf-8",
            ),
        )
        assert m["files"]["stars.json"]["entries"] == 2
        assert m["files"]["eclipses.json"]["entries"] == 2
        assert m["files"]["stars.json"]["updated"]
        assert m["files"]["stars.json"]["source"]

    def test_no_change_keeps_updated_stamp(
        self, tmp_path, monkeypatch,
    ):
        self._setup(tmp_path, monkeypatch)
        update_data.update_manifest({"stars.json": True})

        manifest_path = tmp_path / "manifest.json"
        m = json.loads(
            manifest_path.read_text(encoding="utf-8"),
        )
        m["files"]["stars.json"]["updated"] = "2001-01-01"
        manifest_path.write_text(
            json.dumps(m, indent=2), encoding="utf-8",
        )

        update_data.update_manifest({"stars.json": False})
        after = json.loads(
            manifest_path.read_text(encoding="utf-8"),
        )
        assert (
            after["files"]["stars.json"]["updated"]
            == "2001-01-01"
        )


def _sep_arcsec(ra1, dec1, ra2, dec2):
    return update_stars._angular_sep_deg(ra1, dec1, ra2, dec2) * 3600.0


class TestEpochPropagation:
    """Every source is moved to epoch J2000.0 from its own epoch.

    In 2026 VizieR stopped applying proper motion to its computed
    J2000 columns for the Gliese catalogue, which shifted every
    fast mover by fifty years of motion and duplicated ~300 stars
    in one refresh. Positions are now derived in-house.
    """

    def test_gaia_epoch_2016_reaches_simbad_j2000(self):
        # Barnard's Star, Gaia DR3 4472832130942575872.
        ra, dec = update_stars.propagate_to_j2000(
            np.array([269.44850253]), np.array([4.73942005]),
            np.array([-801.551]), np.array([10362.394]),
            np.array([546.9759]), update_stars.GAIA_DR3_EPOCH_JD,
        )
        assert _sep_arcsec(ra[0], dec[0], 269.45208, 4.69336) < 0.5

    def test_hipparcos_epoch_reaches_simbad_j2000(self):
        # Groombridge 1830, HIP 57939.
        ra, dec = update_stars.propagate_to_j2000(
            np.array([178.23256802]), np.array([37.73280827]),
            np.array([4003.69]), np.array([-5813.00]),
            np.array([109.21]), update_stars.HIPPARCOS_EPOCH_JD,
        )
        assert _sep_arcsec(ra[0], dec[0], 178.24487, 37.71868) < 0.5

    def test_gliese_b1950_row_reaches_j2000(self):
        """Groombridge 1830 as the Gliese catalogue lists it:
        B1950 position, total proper motion and position angle.
        Without the fifty years of motion the star sits ~350
        arcsec away, which is exactly the 2026 regression."""
        ra0, dec0 = update_stars.gliese_b1950_to_icrs(
            ["11 50 06"], ["+38 04.7"],
        )
        assert _sep_arcsec(ra0[0], dec0[0], 178.24487, 37.71868) > 300
        pm, pa = 7.053, math.radians(145.4)
        ra, dec = update_stars.propagate_to_j2000(
            ra0, dec0,
            np.array([pm * 1000 * math.sin(pa)]),
            np.array([pm * 1000 * math.cos(pa)]),
            np.array([116.0]), update_stars.B1950_JD,
        )
        assert _sep_arcsec(ra[0], dec[0], 178.24487, 37.71868) < 10

    def test_zero_proper_motion_is_identity(self):
        ra, dec = update_stars.propagate_to_j2000(
            np.array([10.0]), np.array([-20.0]),
            np.array([0.0]), np.array([0.0]),
            np.array([50.0]), update_stars.HIPPARCOS_EPOCH_JD,
        )
        assert abs(ra[0] - 10.0) < 1e-6
        assert abs(dec[0] + 20.0) < 1e-6

    def test_missing_proper_motion_counts_as_zero(self):
        ra, dec = update_stars.propagate_to_j2000(
            np.array([10.0]), np.array([-20.0]),
            np.array([np.nan]), np.array([np.nan]),
            np.array([np.nan]), update_stars.GAIA_DR3_EPOCH_JD,
        )
        assert abs(ra[0] - 10.0) < 1e-6
        assert abs(dec[0] + 20.0) < 1e-6

    def test_missing_position_stays_missing(self):
        ra, dec = update_stars.propagate_to_j2000(
            np.array([np.nan, 1.0]), np.array([np.nan, 2.0]),
            np.array([0.0, 0.0]), np.array([0.0, 0.0]),
            np.array([50.0, 50.0]), update_stars.HIPPARCOS_EPOCH_JD,
        )
        assert np.isnan(ra[0]) and np.isnan(dec[0])
        assert abs(ra[1] - 1.0) < 1e-6
        ra0, dec0 = update_stars.gliese_b1950_to_icrs([""], [""])
        assert np.isnan(ra0[0]) and np.isnan(dec0[0])


class TestReferencePositions:
    """A fetch at the wrong epoch must fail the run loudly."""

    @staticmethod
    def _refs(source, shift=None):
        stars = []
        for cid, (ra, dec) in update_stars.REFERENCE_POSITIONS[
            source
        ].items():
            if shift and cid == shift[0]:
                ra, dec = shift[1]
            s = _star(cid, 10.0, ra, dec, source=source)
            s["_catalogue_id"] = cid
            stars.append(s)
        return stars

    def test_correct_positions_pass(self):
        for source in ("hipparcos", "gliese", "gaia"):
            assert update_stars.check_reference_positions(
                self._refs(source), source,
            ) == []

    def test_wrong_epoch_is_rejected(self):
        """Gl 451 A where VizieR put it in 2026: the B1950-epoch
        position, 350 arcsec from where it belongs at J2000."""
        stars = self._refs(
            "gliese", shift=("Gl 451 A", (178.1738, 37.8002)),
        )
        errors = update_stars.check_reference_positions(
            stars, "gliese",
        )
        assert len(errors) == 1
        assert "Gl 451 A" in errors[0]
        assert "epoch" in errors[0]

    def test_missing_reference_star_is_rejected(self):
        errors = update_stars.check_reference_positions(
            [], "hipparcos",
        )
        assert len(errors) == 3
        assert all("did not return" in e for e in errors)


class TestGlieseNames:
    """Gliese rows are named by catalogue name plus component."""

    def test_component_is_part_of_designation(self):
        assert update_stars.gliese_name("Gl 451", "A") == "Gl 451 A"
        assert update_stars.gliese_name("Gl 699", "") == "Gl 699"
        assert update_stars.gliese_name("Gl  866", "AB") == "Gl 866 AB"

    def test_component_designations_map_to_common_names(self):
        names = update_stars.GLIESE_COMMON_NAMES
        assert names["Gl 559 A"] == "Alpha Centauri A"
        assert names["Gl 559 B"] == "Alpha Centauri B"
        assert names["Gl 860 B"] == "Kruger 60 B"
        assert names["Gl 725 A"] == "Struve 2398 A"
        assert names["Gl 406"] == "Wolf 359"

    def test_components_of_one_system_never_merge(self):
        """Gl 4 A and Gl 4 B share a row name in the catalogue;
        with the component in the designation they are two
        stars, and the same-source rule keeps them apart."""
        a = _star("Gl 4 A", 37.5, 1.4219, 45.8115, source="gliese")
        b = _star("Gl 4 B", 37.5, 1.4220, 45.8114, source="gliese")
        assert not _same_star(a, b)
        assert len(merge_catalogues([a, b])) == 2


class TestMergedPosition:
    """The merged position follows the most reliable distance."""

    def test_gaia_position_replaces_gliese_position(self):
        gliese = [_star(
            "Gl 451 A", 28.1169, 178.2441, 37.7196, source="gliese",
        )]
        gaia = [_star(
            "Gaia DR3 4034171629042489088", 29.9137,
            178.2449, 37.7187, source="gaia", band="G",
        )]
        merged = merge_catalogues(gliese, gaia)
        assert len(merged) == 1
        assert merged[0]["distance_ly"] == 29.9137
        assert merged[0]["ra_deg"] == 178.2449
        assert merged[0]["dec_deg"] == 37.7187

    def test_hipparcos_position_survives_gliese_merge(self):
        hip = [_star(
            "Delta Pavonis", 19.893, 302.1817, -66.1821,
            source="hipparcos", hip=99240,
        )]
        gliese = [_star(
            "Gl 780", 18.62, 302.1830, -66.1819, source="gliese",
        )]
        merged = merge_catalogues(hip, gliese)
        assert merged[0]["ra_deg"] == 302.1817
        assert merged[0]["dec_deg"] == -66.1821


class TestOverrideMismatch:
    """An override must land on the star it names."""

    def test_override_on_wrong_star_is_flagged(self):
        """HIP 86990 (GJ 693) used to be labelled Kapteyn's Star;
        the override then overwrote GJ 693 with Kapteyn's data
        while the real Kapteyn's Star stayed listed as HIP 24186."""
        s = _star(
            "Kapteyn's Star", 18.954, 266.6426, -57.3190,
            source="hipparcos", hip=86990,
        )
        assert update_stars.apply_overrides([s]) == 1
        errors = [
            e for e in validate_catalogue([s])
            if e.startswith("OVERRIDE_MISMATCH")
        ]
        assert len(errors) == 1
        assert "Kapteyn's Star" in errors[0]

    def test_override_on_right_star_passes(self):
        s = _star(
            "Kapteyn's Star", 12.8308, 77.9191, -45.0184,
            source="hipparcos", hip=24186,
        )
        update_stars.apply_overrides([s])
        assert s["distance_ly"] == 12.777
        assert not [
            e for e in validate_catalogue([s])
            if e.startswith("OVERRIDE_MISMATCH")
        ]


class TestCuratedTables:
    """Static consistency of the hand-verified tables."""

    def test_hip_names_are_unique(self):
        names = list(update_stars.HIP_COMMON_NAMES.values())
        assert len(names) == len(set(names))

    def test_no_name_is_both_curated_and_overridden(self):
        extras = {e["name"] for e in update_stars.EXTRA_STARS}
        assert not extras & set(update_stars.KNOWN_STAR_OVERRIDES)

    def test_curated_coordinates_are_in_range(self):
        rows = list(update_stars.KNOWN_STAR_OVERRIDES.values())
        rows += update_stars.EXTRA_STARS
        for row in rows:
            assert 0 <= row["ra_deg"] < 360
            assert -90 <= row["dec_deg"] <= 90

    def test_reference_stars_agree_across_sources(self):
        """The three reference stars are the same objects in
        every catalogue, so their expected positions must match."""
        refs = update_stars.REFERENCE_POSITIONS
        assert (
            list(refs["hipparcos"].values())
            == list(refs["gliese"].values())
            == list(refs["gaia"].values())
        )
