"""The three date formats the API accepts, one for each endpoint.

Each endpoint takes one format so that a date such as 01/02/2003 is
never ambiguous.
"""

from datetime import date, datetime


def parse_big_endian(text: str) -> date:
    """Parses ``YYYY-MM-DD``."""
    return _parse(text, "%Y-%m-%d", "YYYY-MM-DD")


def parse_middle_endian(text: str) -> date:
    """Parses ``MM/DD/YYYY``."""
    return _parse(text, "%m/%d/%Y", "MM/DD/YYYY")


def parse_little_endian(text: str) -> date:
    """Parses ``DD/MM/YYYY``."""
    return _parse(text, "%d/%m/%Y", "DD/MM/YYYY")


def _parse(text: str, pattern: str, label: str) -> date:
    """Parses ``text`` with a ``strptime`` pattern.

    Raises:
        ValueError: With the message the caller receives as the 422
            detail.
    """
    try:
        return datetime.strptime(text, pattern).date()
    except ValueError:
        raise ValueError(f"Invalid date: {text!r}. Expected {label}.") from None
