"""Writing data/stars.json atomically, and only when it changed."""

import json

from tools.updaters.stars.write import write_stars


def test_unchanged_catalogue_is_not_rewritten(make_star, tmp_path):
    out = tmp_path / "stars.json"
    stars = [make_star("Vega", 25.04, 279.2347, 38.7837)]
    assert write_stars(list(stars), out) is True
    assert write_stars(list(stars), out) is False
    assert list(tmp_path.glob("*.tmp")) == []


def test_changed_catalogue_is_rewritten(make_star, tmp_path):
    out = tmp_path / "stars.json"
    write_stars([make_star("Vega", 25.04, 279.2347, 38.7837)], out)
    changed = write_stars(
        [make_star("Vega", 25.04, 279.2347, 38.7837, exo=1)], out
    )
    assert changed is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["known_exoplanets"] == 1
