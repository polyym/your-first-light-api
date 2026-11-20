"""The entry every stage of the star updater passes along."""

import math

import pytest

from tools.updaters.stars.entry import catalogue_entry, sources_of


def _entry(ra_deg, dec_deg):
    return catalogue_entry(
        name="HIP 87937",
        distance_ly=5.957749,
        spectral_type="M4.0V",
        magnitude=9.5149,
        band="V",
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        source="hipparcos",
        catalogue_id="HIP 87937",
    )


def test_entry_is_rounded_for_writing_and_carries_its_source():
    assert _entry(269.452083, 4.693391) == {
        "name": "HIP 87937",
        "distance_ly": 5.9577,
        "spectral_type": "M4.0V",
        "apparent_magnitude": 9.51,
        "magnitude_band": "V",
        "known_exoplanets": 0,
        "ra_deg": 269.4521,
        "dec_deg": 4.6934,
        "_source": "hipparcos",
        "_pos_source": "hipparcos",
        "_catalogue_id": "HIP 87937",
    }


@pytest.mark.parametrize(
    ("ra_deg", "dec_deg"),
    [(math.nan, 4.6934), (269.4521, math.nan), (math.nan, math.nan)],
    ids=["no-ra", "no-dec", "neither"],
)
def test_entry_with_a_coordinate_missing_has_no_position(ra_deg, dec_deg):
    entry = _entry(ra_deg, dec_deg)

    assert (entry["ra_deg"], entry["dec_deg"]) == (None, None)


@pytest.mark.parametrize(
    ("bookkeeping", "sources"),
    [
        (
            {"_merged_sources": {"gaia", "gliese"}, "_source": "gliese"},
            {"gaia", "gliese"},
        ),
        (
            {"sources": ["gaia", "hipparcos"], "source": "gaia"},
            {"gaia", "hipparcos"},
        ),
        ({"_source": "hipparcos"}, {"hipparcos"}),
        ({"source": "gliese"}, {"gliese"}),
        ({}, set()),
    ],
    ids=["merged", "written-list", "fetched", "written", "curated"],
)
def test_sources_are_read_from_memory_or_from_the_written_file(
    bookkeeping, sources
):
    assert sources_of({"name": "Vega", **bookkeeping}) == sources
