"""Constants that the package metadata and the API's clients depend on."""

import tomllib
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from first_light import constants
from first_light.web.date_formats import (
    parse_big_endian,
    parse_little_endian,
    parse_middle_endian,
)

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
# Clients clamp the wait they read from a 429 to this many seconds.
CLIENT_MAX_WAIT_SECONDS = 60
UI_STAR_LIMIT = 500


def test_api_version_is_the_project_version() -> None:
    with PYPROJECT.open("rb") as file:
        project = tomllib.load(file)["project"]

    assert constants.API_VERSION == project["version"]


def test_rate_limit_window_fits_the_client_wait_clamp() -> None:
    assert constants.RATE_LIMIT_SECONDS <= CLIENT_MAX_WAIT_SECONDS


@pytest.mark.parametrize(
    "star_limit",
    [constants.STAR_LIMIT_DEFAULT, UI_STAR_LIMIT],
    ids=["default", "ui"],
)
def test_star_limit_is_within_the_allowed_range(star_limit: int) -> None:
    assert 1 <= star_limit <= constants.STAR_LIMIT_MAX


@pytest.mark.parametrize(
    ("parse", "text"),
    [
        (parse_big_endian, "1998-11-15"),
        (parse_middle_endian, "11/15/1998"),
        (parse_little_endian, "15/11/1998"),
    ],
    ids=["big-endian", "middle-endian", "little-endian"],
)
def test_date_text_limit_is_the_length_of_each_format(
    parse: Callable[[str], date], text: str
) -> None:
    assert parse(text) == date(1998, 11, 15)
    assert len(text) == constants.DATE_TEXT_MAX_LENGTH
