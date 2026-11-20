"""Fetching, validation and writing of the eclipse catalogue."""

import json
import urllib.error
from datetime import UTC, date, datetime, timedelta

import pytest

from tools.updaters import update_eclipses
from tools.updaters.retry import FETCH_ATTEMPTS
from tools.updaters.update_eclipses import (
    ECLIPSES_PATH,
    fetch_eclipse_dates,
    validate,
    write_eclipses,
)

_PAGE_URL = "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html"


@pytest.fixture
def flaky_page(monkeypatch):
    """Makes the eclipse pages fail before they answer.

    Returns a dict whose ``failures`` sets how many fetches fail first
    and whose ``fetched`` lists the URLs asked for.
    """
    state = {"failures": 0, "fetched": []}

    def fetch_page(url):
        state["fetched"].append(url)
        if len(state["fetched"]) <= state["failures"]:
            raise urllib.error.URLError("connection reset")
        return "<pre>2024 Apr  8  18:18:29</pre>"

    monkeypatch.setattr(update_eclipses, "fetch_page", fetch_page)
    return state


def test_page_is_fetched_again_after_a_failure(flaky_page, retry_waits):
    flaky_page["failures"] = FETCH_ATTEMPTS - 1
    dates = fetch_eclipse_dates([_PAGE_URL], "Solar")
    assert dates == [date(2024, 4, 8)]
    assert len(flaky_page["fetched"]) == FETCH_ATTEMPTS
    assert len(retry_waits) == FETCH_ATTEMPTS - 1


def test_page_failing_every_attempt_is_skipped(flaky_page, retry_waits, capsys):
    flaky_page["failures"] = FETCH_ATTEMPTS
    assert fetch_eclipse_dates([_PAGE_URL], "Solar") == []
    assert len(flaky_page["fetched"]) == FETCH_ATTEMPTS
    assert "Failed to fetch" in capsys.readouterr().out


@pytest.fixture
def shipped_dates() -> tuple[list[date], list[date]]:
    """The solar and lunar dates in data/eclipses.json."""
    data = json.loads(ECLIPSES_PATH.read_text(encoding="utf-8"))
    solar = [date.fromisoformat(d) for d in data["solarEclipses"]]
    lunar = [date.fromisoformat(d) for d in data["lunarEclipses"]]
    return solar, lunar


def test_shipped_catalogue_validates(shipped_dates):
    assert validate(*shipped_dates) == []


def test_missing_1900_lunar_page_fails(shipped_dates):
    """Losing 1900's lunar eclipses barely moves the totals.

    The per-year check still has to fail.
    """
    solar, lunar = shipped_dates
    lunar = [d for d in lunar if d.year != 1900]
    errors = validate(solar, lunar)
    assert any("1900" in e and "lunar" in e for e in errors)


def test_missing_1900_solar_page_fails(shipped_dates):
    solar, lunar = shipped_dates
    solar = [d for d in solar if d.year != 1900]
    errors = validate(solar, lunar)
    assert any("1900" in e and "solar" in e for e in errors)


def test_unsorted_dates_fail(shipped_dates):
    solar, lunar = shipped_dates
    lunar[0], lunar[1] = lunar[1], lunar[0]

    assert "Lunar dates are not sorted" in validate(solar, lunar)


def test_repeated_date_fails(shipped_dates):
    solar, lunar = shipped_dates
    solar.insert(1, solar[0])

    assert "Solar dates contain duplicates" in validate(solar, lunar)


def test_date_in_both_catalogues_fails(shipped_dates):
    solar, lunar = shipped_dates
    lunar = sorted([*lunar, solar[0]])

    assert (
        f"1 date(s) appear in both solar and lunar: [{solar[0]!r}]"
    ) in validate(solar, lunar)


@pytest.mark.parametrize(
    ("days", "refused"), [(24, True), (25, False)], ids=["24-days", "25-days"]
)
def test_eclipses_of_one_kind_under_25_days_apart_fail(
    shipped_dates, days, refused
):
    solar, lunar = shipped_dates
    extra = solar[0] + timedelta(days=days)
    solar.insert(1, extra)

    error = (
        f"Solar eclipses {solar[0]} and {extra} are only {days} days apart "
        "(minimum ~29.5)"
    )
    assert (error in validate(solar, lunar)) is refused


@pytest.mark.parametrize(
    ("kind", "missing"),
    [("solar", date(2024, 4, 8)), ("lunar", date(2022, 11, 8))],
    ids=["solar", "lunar"],
)
def test_missing_well_known_eclipse_fails(shipped_dates, kind, missing):
    solar, lunar = (
        [d for d in dates if d != missing] for dates in shipped_dates
    )

    assert f"Known {kind} eclipse {missing} is missing" in validate(
        solar, lunar
    )


@pytest.mark.parametrize(
    ("count", "refused"),
    [(439, True), (440, False), (470, False), (471, True)],
    ids=["439", "440", "470", "471"],
)
def test_count_outside_440_to_470_fails(shipped_dates, count, refused):
    solar, lunar = shipped_dates
    padding = [solar[-1] + timedelta(days=n) for n in range(1, 30)]
    solar = [*solar, *padding][:count]

    error = f"Solar count {count} outside expected range 440-470"
    assert (error in validate(solar, lunar)) is refused


def test_generated_stamp_is_the_utc_date(tmp_path, monkeypatch):
    """As the manifest dates a change, whatever the machine's zone."""

    class LateOnNewYearsEve(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 12, 31, 23, 30, tzinfo=UTC)

    monkeypatch.setattr(update_eclipses, "datetime", LateOnNewYearsEve)
    out = tmp_path / "eclipses.json"

    write_eclipses([date(2024, 4, 8)], [date(2022, 11, 8)], out)

    stamp = json.loads(out.read_text(encoding="utf-8"))["generated"]
    assert stamp == "2026-12-31"


def test_unchanged_dates_keep_generated_stamp(tmp_path):
    """A rerun with the same dates leaves the file, stamp and all."""
    out = tmp_path / "eclipses.json"
    solar = [date(2024, 4, 8)]
    lunar = [date(2022, 11, 8)]
    assert write_eclipses(solar, lunar, out) is True

    data = json.loads(out.read_text(encoding="utf-8"))
    data["generated"] = "2001-01-01"
    out.write_text(json.dumps(data), encoding="utf-8")
    assert write_eclipses(solar, lunar, out) is False

    after = json.loads(out.read_text(encoding="utf-8"))
    assert after["generated"] == "2001-01-01"
    assert list(tmp_path.glob("*.tmp")) == []
