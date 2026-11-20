"""Fixtures shared by the data updaters' tests."""

import pytest

from tools.updaters import retry


@pytest.fixture
def retry_waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Records the waits between fetch attempts instead of sleeping."""
    waits: list[float] = []
    monkeypatch.setattr(retry.time, "sleep", waits.append)
    return waits
