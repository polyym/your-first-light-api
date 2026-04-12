"""Tests for date parsing functions."""

from datetime import date

import pytest

from src.app import (
    parse_big_endian,
    parse_little_endian,
    parse_middle_endian,
)


class TestParsers:
    """Unit tests for the date parsing functions in ``src.app``."""

    def test_big_endian(self):
        assert parse_big_endian("2000-06-15") == date(2000, 6, 15)

    def test_middle_endian(self):
        assert parse_middle_endian("06/15/2000") == date(2000, 6, 15)

    def test_little_endian(self):
        assert parse_little_endian("15/06/2000") == date(2000, 6, 15)

    def test_big_endian_invalid(self):
        with pytest.raises(ValueError):
            parse_big_endian("15/06/2000")

    def test_middle_endian_invalid(self):
        with pytest.raises(ValueError):
            parse_middle_endian("2000-06-15")
