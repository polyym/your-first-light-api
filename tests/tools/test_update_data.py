"""The manifest bookkeeping and run summary in tools/update_data.py."""

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from tools import update_data

# The manifest dates a change in UTC. The clock stands where a machine
# ahead of UTC already reads the next day.
TODAY = "2026-12-31"


class LateOnNewYearsEve(datetime):
    """A clock stopped at 23:30 UTC on 31 December 2026."""

    @classmethod
    def now(cls, tz=None):
        utc_now = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
        if tz is None:
            return (utc_now + timedelta(hours=14)).replace(tzinfo=None)
        return utc_now.astimezone(tz)


def _star(name, distance_ly, ra_deg, dec_deg, spectral_type="M0V", planets=0):
    return {
        "name": name,
        "distance_ly": distance_ly,
        "spectral_type": spectral_type,
        "known_exoplanets": planets,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
    }


VEGA = _star("Vega", 25.04, 279.2347, 38.7837)
SIRIUS = _star("Sirius A", 8.6, 101.2872, -16.7161)


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _manifest_files(data_dir):
    path = data_dir / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))["files"]


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """A data directory with two stars and two eclipses, late on TODAY."""
    monkeypatch.setattr(update_data, "datetime", LateOnNewYearsEve)
    monkeypatch.setattr(update_data, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        update_data, "_MANIFEST_PATH", tmp_path / "manifest.json"
    )
    _write(tmp_path / "stars.json", [VEGA, SIRIUS])
    _write(
        tmp_path / "eclipses.json",
        {"solarEclipses": ["2024-04-08"], "lunarEclipses": ["2022-11-08"]},
    )
    return tmp_path


def test_manifest_created_with_counts(data_dir):
    changed = update_data.update_manifest(
        {"stars.json": True, "eclipses.json": True}
    )
    assert changed is True
    files = _manifest_files(data_dir)
    assert files["stars.json"]["entries"] == 2
    assert files["eclipses.json"]["entries"] == 2
    assert files["stars.json"]["updated"]
    assert files["stars.json"]["source"]


def test_no_change_keeps_updated_stamp(data_dir):
    manifest_path = data_dir / "manifest.json"
    update_data.update_manifest({"stars.json": True})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["stars.json"]["updated"] = "2001-01-01"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    update_data.update_manifest({"stars.json": False})

    assert _manifest_files(data_dir)["stars.json"]["updated"] == "2001-01-01"


def test_new_entry_takes_the_files_generated_stamp(data_dir):
    """An unchanged file last changed when it says it was generated."""
    eclipses = json.loads(
        (data_dir / "eclipses.json").read_text(encoding="utf-8")
    )
    eclipses["generated"] = "2026-04-11"
    _write(data_dir / "eclipses.json", eclipses)

    update_data.update_manifest({"eclipses.json": False, "stars.json": False})

    files = _manifest_files(data_dir)
    assert files["eclipses.json"]["updated"] == "2026-04-11"
    # stars.json records no stamp.
    assert files["stars.json"]["updated"] == TODAY


def test_changed_file_is_dated_today_whatever_its_stamp(data_dir):
    eclipses = json.loads(
        (data_dir / "eclipses.json").read_text(encoding="utf-8")
    )
    eclipses["generated"] = "2001-01-01"
    _write(data_dir / "eclipses.json", eclipses)

    update_data.update_manifest({"eclipses.json": True})

    assert _manifest_files(data_dir)["eclipses.json"]["updated"] == TODAY


def test_corrupt_manifest_is_never_replaced(data_dir):
    """Merge-conflict markers, as an automated pull request can leave."""
    corrupt = '<<<<<<< HEAD\n{"files": {}}\n=======\n{}\n>>>>>>> refresh\n'
    manifest_path = data_dir / "manifest.json"
    manifest_path.write_text(corrupt, encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        update_data.update_manifest({"stars.json": False})

    assert manifest_path.read_text(encoding="utf-8") == corrupt


@pytest.mark.parametrize(
    "manifest",
    ["[]", '{"files": []}', '{"files": {"stars.json": []}}'],
    ids=["list", "files-list", "entry-list"],
)
def test_manifest_of_the_wrong_shape_fails_the_run_before_any_update(
    refresh, data_dir, capsys, manifest
):
    (data_dir / "manifest.json").write_text(manifest, encoding="utf-8")
    stars_before = (data_dir / "stars.json").read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        refresh()

    assert exit_info.value.code == 1
    assert 'not an object with a "files" object' in capsys.readouterr().out
    assert (data_dir / "stars.json").read_text(encoding="utf-8") == (
        stars_before
    )
    assert (data_dir / "manifest.json").read_text(encoding="utf-8") == manifest


def test_shipped_manifest_dates_eclipses_by_their_generated_stamp():
    manifest = json.loads(
        update_data._MANIFEST_PATH.read_text(encoding="utf-8")
    )
    eclipses = json.loads(
        (update_data._DATA_DIR / "eclipses.json").read_text(encoding="utf-8")
    )
    updated = manifest["files"]["eclipses.json"]["updated"]
    assert updated == eclipses["generated"]


def test_shipped_manifest_is_as_a_run_that_changed_nothing_leaves_it(
    tmp_path, monkeypatch
):
    """Byte for byte, so that a refresh's diff shows only what it changed."""
    for name in ("eclipses.json", "manifest.json", "stars.json"):
        shutil.copy(update_data._DATA_DIR / name, tmp_path / name)
    monkeypatch.setattr(update_data, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        update_data, "_MANIFEST_PATH", tmp_path / "manifest.json"
    )
    shipped = (tmp_path / "manifest.json").read_bytes()

    rewritten = update_data.update_manifest(
        {"eclipses.json": False, "stars.json": False}
    )

    assert rewritten is False
    assert (tmp_path / "manifest.json").read_bytes() == shipped


def test_manifest_without_files_is_filled_in(refresh, data_dir):
    (data_dir / "manifest.json").write_text("{}", encoding="utf-8")

    refresh()

    assert set(_manifest_files(data_dir)) == {"eclipses.json", "stars.json"}


def test_summary_lists_near_stars_added_removed_and_renamed():
    far = _star("HIP 1", 100.0, 1.0, 1.0)
    before = [
        VEGA,
        _star("Gaia DR3 1", 12.0, 10.0, 10.0),
        _star("Gl 9", 29.9, 50.0, 50.0),
        _star("Gl 8", 20.0, 60.0, 60.0),
        far,
    ]
    after = [
        VEGA,
        _star("HIP 5", 12.1, 10.0, 10.0001),
        _star("Gl 9", 30.2, 50.0, 50.0),
        _star("Gaia DR3 7", 15.0, 70.0, 70.0),
        far,
    ]

    summary = update_data.data_summary(
        {"stars.json": before}, {"stars.json": after}
    )

    assert "| stars.json | 5 | 5 |" in summary
    assert "Stars within 30 ly: 4 before, 3 after." in summary
    assert "Added (1):\n- Gaia DR3 7, 15.0 ly\n" in summary
    assert (
        "Removed (2):\n- Gl 8, 20.0 ly\n- Gl 9, 29.9 ly (now 30.2 ly)\n"
    ) in summary
    assert "Renamed (1):\n- Gaia DR3 1 -> HIP 5, 12.1 ly\n" in summary


def test_summary_lists_near_spectral_type_changes():
    """Types that change within 30 ly, near on either side; none beyond."""
    before = [
        _star("HIP 85523", 14.8491, 262.1664, -46.8952, "K5"),
        _star("Gaia DR3 4", 15.88, 10.0, 10.0, "M (est)"),
        _star("Gl 9", 30.5, 50.0, 50.0, "K2V"),
        _star("Gl 7", 29.5, 40.0, 40.0, "K1V"),
        _star("HIP 1", 100.0, 1.0, 1.0, "G2V"),
        VEGA,
    ]
    after = [
        _star("HIP 85523", 14.8491, 262.1664, -46.8952, "M3"),
        _star("Gaia DR3 4", 15.88, 10.0, 10.0, ""),
        _star("Gl 9", 29.9, 50.0, 50.0, "K3V"),
        _star("Gl 7", 30.4, 40.0, 40.0, "K2V"),
        _star("HIP 1", 100.0, 1.0, 1.0, "G5V"),
        VEGA,
    ]

    summary = update_data.data_summary(
        {"stars.json": before}, {"stars.json": after}
    )

    assert (
        "Spectral type changed (4):\n"
        "- HIP 85523, 14.8491 ly: K5 -> M3\n"
        "- Gaia DR3 4, 15.88 ly: M (est) -> no type\n"
        "- Gl 9, 29.9 ly: K2V -> K3V\n"
        "- Gl 7, 30.4 ly: K1V -> K2V\n"
    ) in summary
    assert "HIP 1" not in summary


def test_summary_gives_a_renamed_stars_type_change():
    before = [_star("HIP 1", 10.0, 50.0, 20.0, "M3V")]
    after = [_star("Gaia DR3 9", 10.1, 50.0, 20.001, "M (est)")]

    summary = update_data.data_summary(
        {"stars.json": before}, {"stars.json": after}
    )

    assert "- HIP 1 -> Gaia DR3 9, 10.1 ly (M3V -> M (est))\n" in summary
    assert "No star within" not in summary


def test_summary_gives_a_renamed_stars_planet_count_change():
    before = [_star("HIP 1", 10.0, 50.0, 20.0, "M3V", planets=2)]
    after = [_star("Gaia DR3 9", 10.1, 50.0, 20.001, "M3V")]

    summary = update_data.data_summary(
        {"stars.json": before}, {"stars.json": after}
    )

    assert "- HIP 1 -> Gaia DR3 9, 10.1 ly (planets 2 -> 0)\n" in summary


def test_summary_gives_planet_counts():
    """The total, and each near star whose count changed; none beyond."""
    before = [
        _star("Gl 876", 15.2, 343.3, -14.3, "M4V", planets=3),
        _star("HIP 2", 40.0, 2.0, 2.0, "G2V", planets=1),
        VEGA,
    ]
    after = [
        _star("Gl 876", 15.2, 343.3, -14.3, "M4V", planets=4),
        _star("HIP 2", 40.0, 2.0, 2.0, "G2V", planets=2),
        VEGA,
    ]

    summary = update_data.data_summary(
        {"stars.json": before}, {"stars.json": after}
    )

    assert "Known exoplanets: 4 before, 6 after.\n" in summary
    assert "Known exoplanets changed (1):\n- Gl 876, 15.2 ly: 3 -> 4\n" in (
        summary
    )
    assert "HIP 2" not in summary


def test_rename_pairs_the_closest_names_first():
    """HIP 7 is 9 arcsec from Gaia DR3 1 but 1.8 from Gaia DR3 2."""
    before = [
        _star("Gaia DR3 1", 12.0, 10.0, 10.0),
        _star("Gaia DR3 2", 12.0, 10.0, 10.003),
    ]
    after = [
        _star("HIP 7", 12.0, 10.0, 10.0025),
        _star("HIP 8", 12.0, 10.0, 10.0045),
    ]

    summary = update_data.data_summary(
        {"stars.json": before}, {"stars.json": after}
    )

    assert (
        "Renamed (2):\n"
        "- Gaia DR3 2 -> HIP 7, 12.0 ly\n"
        "- Gaia DR3 1 -> HIP 8, 12.0 ly\n"
    ) in summary
    assert "Added" not in summary
    assert "Removed" not in summary


def test_star_that_only_crossed_30_ly_is_never_half_of_a_rename():
    """Gl 9 comes within 30 ly, 4 arcsec from where Gl 8 was."""
    at_30_ly = _star("HIP 30", 30.0, 80.0, 80.0)
    before = [
        _star("Gaia DR3 1", 12.0, 10.0, 10.0),
        _star("Gl 9", 30.5, 50.0, 50.0),
        _star("Gl 8", 29.0, 50.0, 50.001),
        at_30_ly,
    ]
    after = [
        _star("HIP 5", 12.1, 10.0, 10.0001),
        _star("Gl 9", 29.9, 50.0, 50.0),
        at_30_ly,
    ]

    summary = update_data.data_summary(
        {"stars.json": before}, {"stars.json": after}
    )

    assert "Stars within 30 ly: 3 before, 3 after." in summary
    assert "Added (1):\n- Gl 9, 29.9 ly (was 30.5 ly)\n" in summary
    assert "Removed (1):\n- Gl 8, 29.0 ly\n" in summary
    assert "Renamed (1):\n- Gaia DR3 1 -> HIP 5, 12.1 ly\n" in summary


def test_summary_of_a_run_that_changed_nothing():
    eclipses = {"solarEclipses": ["2024-04-08"], "lunarEclipses": []}
    data = {"stars.json": [VEGA, SIRIUS], "eclipses.json": eclipses}

    summary = update_data.data_summary(data, data)

    assert "| eclipses.json | 1 | 1 |\n| stars.json | 2 | 2 |\n" in summary
    assert (
        "Stars within 30 ly: 2 before, 2 after.\n"
        "\n"
        "No star within 30 ly was added, removed or renamed."
    ) in summary


def test_summary_of_an_eclipses_run_has_no_star_section():
    eclipses = {"solarEclipses": ["2024-04-08"], "lunarEclipses": []}
    summary = update_data.data_summary(
        {"eclipses.json": None}, {"eclipses.json": eclipses}
    )
    assert "| eclipses.json | none | 1 |" in summary
    assert "Stars within" not in summary


@pytest.fixture
def refresh(data_dir, monkeypatch):
    """Runs main() with a stars updater that adds Proxima Centauri."""
    proxima = _star("Proxima Centauri", 4.2465, 217.4289, -62.6795)

    def run_updater(updater):
        if updater.name == "stars":
            _write(data_dir / "stars.json", [proxima, VEGA, SIRIUS])
        return True

    monkeypatch.setattr(update_data, "_run_updater", run_updater)
    monkeypatch.setattr(update_data, "_missing_packages", lambda pkgs: [])
    monkeypatch.setattr(sys, "argv", ["update_data.py"])
    return update_data.main


def test_run_writes_the_summary_where_the_environment_says(
    refresh, tmp_path, monkeypatch, capsys
):
    path = tmp_path / "data-summary.md"
    monkeypatch.setenv(update_data.SUMMARY_PATH_ENV, str(path))

    refresh()

    summary = path.read_text(encoding="utf-8")
    assert "| stars.json | 2 | 3 |" in summary
    assert "Added (1):\n- Proxima Centauri, 4.2465 ly\n" in summary
    assert "No star within" not in summary
    assert summary in capsys.readouterr().out


def test_run_dates_only_the_file_that_changed(refresh, data_dir, capsys):
    """The stars updater adds a star; the eclipses stay as they were."""
    unchanged_since = {"updated": "2001-01-01"}
    _write(
        data_dir / "manifest.json",
        {
            "files": {
                "eclipses.json": dict(unchanged_since),
                "stars.json": dict(unchanged_since),
            }
        },
    )

    refresh()

    files = _manifest_files(data_dir)
    assert files["stars.json"]["updated"] == TODAY
    assert files["eclipses.json"]["updated"] == "2001-01-01"
    assert "\nData changed: stars.json\n" in capsys.readouterr().out


def test_run_that_changes_nothing_says_so(refresh, monkeypatch, capsys):
    monkeypatch.setattr(update_data, "_run_updater", lambda updater: True)

    refresh()

    out = capsys.readouterr().out
    assert "All data already up to date; nothing to commit." in out
    assert "Data changed" not in out


def test_failed_updater_fails_the_run_before_the_manifest_and_summary(
    refresh, data_dir, monkeypatch, capsys
):
    """A scheduled run that exits with 1 opens no pull request."""
    monkeypatch.setenv(
        update_data.SUMMARY_PATH_ENV, str(data_dir / "data-summary.md")
    )
    monkeypatch.setattr(
        update_data, "_run_updater", lambda updater: updater.name != "stars"
    )

    with pytest.raises(SystemExit) as exit_info:
        refresh()

    assert exit_info.value.code == 1
    assert "  eclipses     OK\n  stars        FAILED\n" in (
        capsys.readouterr().out
    )
    assert sorted(p.name for p in data_dir.iterdir()) == [
        "eclipses.json",
        "stars.json",
    ]


def test_named_updater_runs_alone(refresh, data_dir, monkeypatch):
    ran = []

    def run_updater(updater):
        ran.append(updater.name)
        return True

    monkeypatch.setattr(update_data, "_run_updater", run_updater)
    monkeypatch.setattr(sys, "argv", ["update_data.py", "Eclipses"])

    refresh()

    assert ran == ["eclipses"]
    assert set(_manifest_files(data_dir)) == {"eclipses.json"}


def test_unknown_updater_is_refused_with_the_names_to_choose_from(
    refresh, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["update_data.py", "moons"])

    with pytest.raises(SystemExit) as exit_info:
        refresh()

    assert exit_info.value.code == 1
    assert "Unknown updater: 'moons'\nAvailable: eclipses, stars\n" in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize(
    ("status", "succeeded"),
    [(0, True), (1, False), (2, False)],
    ids=["exit-0", "exit-1", "exit-2"],
)
def test_updater_succeeds_only_when_its_process_exits_with_0(
    monkeypatch, status, succeeded
):
    commands = []

    def run(command, cwd):
        commands.append((command, cwd))
        return subprocess.CompletedProcess(command, status)

    monkeypatch.setattr(update_data.subprocess, "run", run)
    stars = update_data._Updater(
        "stars", "tools.updaters.stars", ["astroquery"], "stars.json"
    )

    assert update_data._run_updater(stars) is succeeded
    assert commands == [
        (
            [sys.executable, "-u", "-m", "tools.updaters.stars"],
            str(update_data._ROOT),
        )
    ]


def test_missing_packages_are_those_that_cannot_be_imported():
    assert update_data._missing_packages(["json", "no_such_package"]) == [
        "no_such_package"
    ]


def test_corrupt_manifest_fails_the_run_before_any_update(
    refresh, data_dir, capsys
):
    (data_dir / "manifest.json").write_text("<<<<<<< HEAD\n", encoding="utf-8")
    stars_before = (data_dir / "stars.json").read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        refresh()

    assert exit_info.value.code == 1
    assert "manifest.json is not a usable manifest: Expecting value" in (
        capsys.readouterr().out
    )
    assert (data_dir / "stars.json").read_text(encoding="utf-8") == (
        stars_before
    )


def test_missing_package_is_reported_with_the_uv_command(
    refresh, monkeypatch, capsys
):
    monkeypatch.setattr(
        update_data, "_missing_packages", lambda pkgs: list(pkgs)
    )
    monkeypatch.setattr(sys, "argv", ["update_data.py", "stars"])

    with pytest.raises(SystemExit) as exit_info:
        refresh()

    assert exit_info.value.code == 1
    assert (
        "Missing required packages: astroquery\n"
        "Install them into the project environment with:\n"
        "  uv sync --group catalogue\n"
    ) in capsys.readouterr().out


def test_run_writes_no_summary_file_unless_asked(
    refresh, tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv(update_data.SUMMARY_PATH_ENV, raising=False)

    refresh()

    assert "Added (1):" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "eclipses.json",
        "manifest.json",
        "stars.json",
    ]
