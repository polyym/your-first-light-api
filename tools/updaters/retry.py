"""Retrying upstream fetches, which fail now and then for a few minutes."""

import time
from collections.abc import Callable

# Enough to ride out a dropped connection or a server restart; a host
# that is down for longer fails the run, which the next refresh retries.
FETCH_ATTEMPTS = 3
FIRST_RETRY_DELAY_SECONDS = 10.0
RETRY_DELAY_GROWTH_FACTOR = 3.0


def with_retries[T](fetch: Callable[[], T], label: str) -> T:
    """Calls ``fetch`` until it returns, at most ``FETCH_ATTEMPTS`` times.

    Each failure but the last is printed with ``label`` and followed by
    a wait, ``FIRST_RETRY_DELAY_SECONDS`` at first and
    ``RETRY_DELAY_GROWTH_FACTOR`` times longer each time after.

    Returns:
        What ``fetch`` returned.

    Raises:
        Exception: Whatever the last attempt raised.
    """
    delay_seconds = FIRST_RETRY_DELAY_SECONDS
    for attempt in range(1, FETCH_ATTEMPTS):
        try:
            return fetch()
        except Exception as e:
            print(
                f"  WARNING: {label}: attempt {attempt} of {FETCH_ATTEMPTS} "
                f"failed: {e}; retrying in {delay_seconds:.0f} s",
                flush=True,
            )
            time.sleep(delay_seconds)
            delay_seconds *= RETRY_DELAY_GROWTH_FACTOR
    return fetch()
