"""The Gliese fetch: designations, systems and left-out rows."""

from astropy.table import MaskedColumn, Table

from tools.updaters.stars import gliese
from tools.updaters.stars.gliese import gliese_name
from tools.updaters.stars.validate import MAX_RADIUS_LY

# Barnard's Star, Alpha Centauri A and B, and Capella's second giant,
# as the catalogue gives them.
_ROWS = {
    "Name": ["Gl 699", "Gl 559", "Gl 559", "Gl 194"],
    "Comp": MaskedColumn(["", "A", "B", "B"], mask=[True, False, False, False]),
    "RAB1950": ["17 55 23", "14 36 11", "14 36 11", "05 12 59"],
    "DEB1950": ["+04 33.3", "-60 37.8", "-60 37.8", "+45 57.0"],
    "pm": [10.31, 3.689, 3.689, 0.431],
    "pmPA": [355.8, 281.1, 281.1, 169.2],
    "plx": [545.3, 749.0, 749.0, 79.0],
    "e_plx": [1.0, 4.7, 4.7, 4.2],
    "Vmag": [9.55, 0.01, 1.34, 0.96],
    "Sp": ["M5 V", "G2 V", "K0 V", "G0 III"],
}


def _fetch(monkeypatch) -> dict[str, dict]:
    table = Table(_ROWS)
    monkeypatch.setattr(gliese, "query_catalogue", lambda *a, **k: table)
    return {s["_catalogue_id"]: s for s in gliese.fetch_gliese(MAX_RADIUS_LY)}


def test_component_is_part_of_designation():
    assert gliese_name("Gl 451", "A") == "Gl 451 A"
    assert gliese_name("Gl 699", "") == "Gl 699"
    assert gliese_name("Gl  866", "AB") == "Gl 866 AB"


def test_component_carries_its_system(monkeypatch):
    stars = _fetch(monkeypatch)
    assert stars["Gl 559 A"]["_gliese_system"] == "Gl 559"
    assert stars["Gl 559 B"]["_gliese_system"] == "Gl 559"
    assert "_gliese_system" not in stars["Gl 699"]


def test_row_another_entry_already_holds_is_left_out(monkeypatch):
    """Capella's Gl 194 B, whose light HIP 24608 already holds."""
    assert set(_fetch(monkeypatch)) == {"Gl 699", "Gl 559 A", "Gl 559 B"}
