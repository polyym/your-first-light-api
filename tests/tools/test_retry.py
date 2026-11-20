"""Retrying upstream fetches with growing waits."""

import pytest

from tools.updaters.retry import (
    FETCH_ATTEMPTS,
    FIRST_RETRY_DELAY_SECONDS,
    RETRY_DELAY_GROWTH_FACTOR,
    with_retries,
)


class _Flaky:
    """A fetch that fails a given number of times, then answers."""

    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError(f"failure {self.calls}")
        return "answer"


def test_first_answer_needs_no_wait(retry_waits):
    fetch = _Flaky(failures=0)
    assert with_retries(fetch, "test") == "answer"
    assert fetch.calls == 1
    assert retry_waits == []


def test_answer_after_failures_waits_longer_each_time(retry_waits, capsys):
    fetch = _Flaky(failures=FETCH_ATTEMPTS - 1)
    assert with_retries(fetch, "HIPPARCOS query") == "answer"
    assert fetch.calls == FETCH_ATTEMPTS
    assert retry_waits == [
        FIRST_RETRY_DELAY_SECONDS * RETRY_DELAY_GROWTH_FACTOR**n
        for n in range(FETCH_ATTEMPTS - 1)
    ]
    assert "HIPPARCOS query: attempt 1" in capsys.readouterr().out


def test_gives_up_with_the_last_error(retry_waits):
    fetch = _Flaky(failures=FETCH_ATTEMPTS)
    with pytest.raises(ConnectionError, match=f"failure {FETCH_ATTEMPTS}"):
        with_retries(fetch, "test")
    assert fetch.calls == FETCH_ATTEMPTS
    assert len(retry_waits) == FETCH_ATTEMPTS - 1
