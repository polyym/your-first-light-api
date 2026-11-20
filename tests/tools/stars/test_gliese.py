"""Designations of Gliese catalogue rows."""

from tools.updaters.stars.gliese import gliese_name


def test_component_is_part_of_designation():
    assert gliese_name("Gl 451", "A") == "Gl 451 A"
    assert gliese_name("Gl 699", "") == "Gl 699"
    assert gliese_name("Gl  866", "AB") == "Gl 866 AB"
