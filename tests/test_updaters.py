"""Offline unit tests for the data updater tools.

These exercise the merge, validation, and write logic with
synthetic data; no network access is required.
"""

import json

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

    def test_proper_motion_drift_still_merges(self):
        """Barnard's Star drifts ~0.07 deg between the
        HIPPARCOS and Gaia epochs; the separation window must
        absorb that."""
        a = _star(
            "Barnard's Star", 5.9577, 269.4521, 4.6934,
            source="hipparcos", hip=87937,
        )
        b = _star(
            "Gaia DR3 4472832130942575872", 5.978,
            269.4486, 4.7398, source="gaia", band="G",
        )
        assert _same_star(a, b)

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
        a = _star("Kruger 60 A", 13.149, 331.0918, 57.6962)
        b = _star("Kruger 60 B", 13.149, 331.0918, 57.6962)
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
