"""The HIPPARCOS fetch: rows to entries."""

import pytest
from astropy.table import Table

from tools.updaters.stars import hipparcos
from tools.updaters.stars.validate import MAX_RADIUS_LY


def test_spurious_entries_are_left_out(monkeypatch):
    """The seven rows as HIPPARCOS has them, and Barnard's Star.

    Each of the seven is within 40 light-years by its HIPPARCOS
    parallax, of five standard errors or more. Gaia has no source where
    HIP 114110 and HIP 114176 are listed, and puts the other five
    between 200 and 7,900 light-years away.
    """
    table = Table(
        {
            "HIP": [21000, 82724, 82725, 85605, 98681, 114110, 114176, 87937],
            "RAICRS": [
                67.55216585,
                253.63222815,
                253.63394770,
                262.40078667,
                300.64939243,
                346.66203219,
                346.83136570,
                269.45402305,
            ],
            "DEICRS": [
                5.29852669,
                -62.40023361,
                -62.40374141,
                24.65322144,
                -50.04937722,
                -14.87239655,
                -32.26819891,
                4.66828815,
            ],
            "pmRA": [
                106.9,
                294.47,
                254.79,
                97.33,
                334.48,
                112.27,
                -223.58,
                -797.84,
            ],
            "pmDE": [
                119.86,
                205.48,
                173.56,
                348.92,
                -311.41,
                83.24,
                -30.45,
                10326.93,
            ],
            "Plx": [
                84.76,
                109.57,
                203.01,
                202.69,
                84.75,
                216.52,
                147.95,
                549.01,
            ],
            "e_Plx": [4.74, 20.12, 29.27, 39.48, 11.17, 18.28, 13.76, 1.58],
            "Vmag": [9.83, 11.85, 11.72, 11.39, 9.92, 12.24, 12.28, 9.54],
            "SpType": ["F8+...", "Mp", "", "", "", "", "", "sdM4"],
        }
    )
    monkeypatch.setattr(hipparcos, "query_catalogue", lambda *a, **k: table)

    (star,) = hipparcos.fetch_hipparcos(MAX_RADIUS_LY)

    assert star["name"] == "Barnard's Star"
    assert star["_hip_id"] == 87937
    assert star["distance_ly"] == pytest.approx(5.9408, abs=1e-3)
