"""Tests for the three date formats the endpoints accept."""

from datetime import date

import pytest

from first_light.web.date_formats import (
    parse_big_endian,
    parse_little_endian,
    parse_middle_endian,
)


@pytest.mark.parametrize(
    ("parse", "text", "expected"),
    [
        (parse_big_endian, "1998-11-15", date(1998, 11, 15)),
        (parse_big_endian, "2000-02-29", date(2000, 2, 29)),
        (parse_big_endian, "0001-01-01", date(1, 1, 1)),
        (parse_big_endian, "9999-12-31", date(9999, 12, 31)),
        # A day or month without its leading zero is accepted.
        (parse_big_endian, "1998-11-1", date(1998, 11, 1)),
        (parse_big_endian, "1998-1-5", date(1998, 1, 5)),
        (parse_middle_endian, "11/15/1998", date(1998, 11, 15)),
        (parse_middle_endian, "02/29/2000", date(2000, 2, 29)),
        (parse_little_endian, "15/11/1998", date(1998, 11, 15)),
        (parse_little_endian, "29/02/2000", date(2000, 2, 29)),
    ],
    ids=[
        "big-endian",
        "big-endian-leap-day",
        "big-endian-year-one",
        "big-endian-last-day",
        "big-endian-one-digit-day",
        "big-endian-one-digit-month",
        "middle-endian",
        "middle-endian-leap-day",
        "little-endian",
        "little-endian-leap-day",
    ],
)
def test_valid_date_parses(parse, text, expected):
    assert parse(text) == expected


@pytest.mark.parametrize(
    ("parse", "expected"),
    [
        (parse_middle_endian, date(2003, 1, 2)),
        (parse_little_endian, date(2003, 2, 1)),
    ],
    ids=["middle-endian-month-first", "little-endian-day-first"],
)
def test_ambiguous_slash_date_follows_the_endpoint_format(parse, expected):
    assert parse("01/02/2003") == expected


@pytest.mark.parametrize(
    ("parse", "text", "message"),
    [
        (
            parse_big_endian,
            "1998-02-30",
            "Invalid date: '1998-02-30'. Expected YYYY-MM-DD.",
        ),
        (
            parse_big_endian,
            "1900-02-29",
            "Invalid date: '1900-02-29'. Expected YYYY-MM-DD.",
        ),
        (
            parse_big_endian,
            "1998-13-01",
            "Invalid date: '1998-13-01'. Expected YYYY-MM-DD.",
        ),
        (
            parse_big_endian,
            "15/11/1998",
            "Invalid date: '15/11/1998'. Expected YYYY-MM-DD.",
        ),
        (
            parse_big_endian,
            "1998-11-15T00",
            "Invalid date: '1998-11-15T00'. Expected YYYY-MM-DD.",
        ),
        (parse_big_endian, "", "Invalid date: ''. Expected YYYY-MM-DD."),
        # Other ISO 8601 forms are refused, as are surrounding spaces.
        (
            parse_big_endian,
            "19981115",
            "Invalid date: '19981115'. Expected YYYY-MM-DD.",
        ),
        (
            parse_big_endian,
            "1998-W46-7",
            "Invalid date: '1998-W46-7'. Expected YYYY-MM-DD.",
        ),
        (
            parse_big_endian,
            "1998-11-1 ",
            "Invalid date: '1998-11-1 '. Expected YYYY-MM-DD.",
        ),
        # repr() quotes text holding an apostrophe in double quotes.
        (
            parse_big_endian,
            "it's",
            'Invalid date: "it\'s". Expected YYYY-MM-DD.',
        ),
        (
            parse_middle_endian,
            "1998-11-15",
            "Invalid date: '1998-11-15'. Expected MM/DD/YYYY.",
        ),
        (
            parse_middle_endian,
            "15/11/1998",
            "Invalid date: '15/11/1998'. Expected MM/DD/YYYY.",
        ),
        (
            parse_middle_endian,
            "02/30/2000",
            "Invalid date: '02/30/2000'. Expected MM/DD/YYYY.",
        ),
        (
            parse_little_endian,
            "11/15/1998",
            "Invalid date: '11/15/1998'. Expected DD/MM/YYYY.",
        ),
        (
            parse_little_endian,
            "31/04/1998",
            "Invalid date: '31/04/1998'. Expected DD/MM/YYYY.",
        ),
        (
            parse_little_endian,
            "1998-11-15",
            "Invalid date: '1998-11-15'. Expected DD/MM/YYYY.",
        ),
    ],
    ids=[
        "big-endian-30-february",
        "big-endian-1900-not-a-leap-year",
        "big-endian-month-13",
        "big-endian-given-slashes",
        "big-endian-trailing-text",
        "big-endian-empty",
        "big-endian-basic-format",
        "big-endian-week-date",
        "big-endian-trailing-space",
        "big-endian-text-with-an-apostrophe",
        "middle-endian-given-big-endian",
        "middle-endian-given-little-endian",
        "middle-endian-30-february",
        "little-endian-given-middle-endian",
        "little-endian-31-april",
        "little-endian-given-big-endian",
    ],
)
def test_invalid_date_names_the_text_and_the_expected_format(
    parse, text, message
):
    with pytest.raises(ValueError) as excinfo:
        parse(text)
    assert str(excinfo.value) == message
