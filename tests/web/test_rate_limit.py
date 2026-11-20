"""Tests for the one-success-every-30-seconds limit on the POST endpoints."""

import asyncio
import threading

import httpx2
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from first_light.app import app
from first_light.constants import MAX_CONCURRENT_COMPUTATIONS
from first_light.web import client_ip, rate_limit, routes
from first_light.web.rate_limit import caller_key

BIG = "/v1/big-endian-first-light"
MIDDLE = "/v1/middle-endian-first-light"
LITTLE = "/v1/little-endian-first-light"
REQUEST = {
    "birthday": "1998-11-15",
    "as_of": "2026-11-18",
    "categories": ["links"],
}
REQUEST_IN_FORMAT = {
    BIG: REQUEST,
    MIDDLE: {**REQUEST, "birthday": "11/15/1998", "as_of": "11/18/2026"},
    LITTLE: {**REQUEST, "birthday": "15/11/1998", "as_of": "18/11/2026"},
}
START = 1_763_000_000.0
# Ample for each step of the concurrent pair below on a loaded machine.
WAIT_LIMIT_SECONDS = 5


class FakeClock:
    """Stands in for the time module; tests move ``now`` by hand."""

    def __init__(self):
        self.now = START

    def monotonic(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    """Stops the rate limiter's clock at START."""
    fake = FakeClock()
    monkeypatch.setattr(rate_limit, "time", fake)
    return fake


@pytest.fixture
def platform_header(monkeypatch):
    """Lets each request name its caller in True-Client-IP."""
    monkeypatch.setattr(client_ip, "CLIENT_IP_HEADER", "True-Client-IP")


def post_as(client, address):
    return client.post(BIG, json=REQUEST, headers={"True-Client-IP": address})


# Each elapsed time is exact in binary, so float error cannot move a
# tenth across a rounding boundary.
@pytest.mark.parametrize(
    ("elapsed", "wait", "retry_after"),
    [
        (0.0, "30.0", "30"),
        (4.75, "25.3", "26"),
        (5.0, "25.0", "25"),
        (29.5, "0.5", "1"),
        (29.96875, "0.1", "1"),
    ],
    ids=[
        "at-once",
        "tenths-round-up",
        "whole-seconds",
        "half-second-left",
        "a-sliver-left-is-a-tenth",
    ],
)
def test_second_request_inside_the_wait_is_told_how_long_to_wait(
    client, clock, elapsed, wait, retry_after
):
    assert client.post(BIG, json=REQUEST).status_code == 200
    clock.now = START + elapsed

    response = client.post(BIG, json=REQUEST)

    assert response.status_code == 429
    assert response.json() == {
        "detail": f"Rate limited. Please wait {wait} seconds before trying "
        "again."
    }
    assert response.headers["retry-after"] == retry_after


@pytest.mark.parametrize(
    ("elapsed", "status"),
    [(29.9, 429), (30.0, 200)],
    ids=["just-inside", "exactly-the-window"],
)
def test_slot_reopens_30_seconds_after_the_last_success(
    client, clock, elapsed, status
):
    client.post(BIG, json=REQUEST)
    clock.now = START + elapsed
    assert client.post(BIG, json=REQUEST).status_code == status


def test_refused_request_does_not_restart_the_wait(client, clock):
    client.post(BIG, json=REQUEST)
    clock.now = START + 29.9
    assert client.post(BIG, json=REQUEST).status_code == 429
    clock.now = START + 30.0
    assert client.post(BIG, json=REQUEST).status_code == 200


@pytest.mark.parametrize("path", [BIG, MIDDLE, LITTLE])
def test_the_three_endpoints_share_one_slot(client, clock, path):
    client.post(BIG, json=REQUEST)
    assert client.post(path, json=REQUEST_IN_FORMAT[path]).status_code == 429


def test_429_carries_cors_and_exposes_retry_after(client, clock):
    client.post(BIG, json=REQUEST)
    response = client.post(
        LITTLE,
        json=REQUEST_IN_FORMAT[LITTLE],
        headers={"Origin": "https://example.org"},
    )
    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-expose-headers"] == "Retry-After"


@pytest.mark.parametrize(
    ("failing", "status"),
    [
        ({"json": {"birthday": "bad"}}, 422),
        (
            {
                "content": b'{"birthday": "\xff\xfe"}',
                "headers": {"Content-Type": "application/json"},
            },
            400,
        ),
    ],
    ids=["unprocessable-422", "not-utf8-400"],
)
def test_failed_request_gives_the_slot_back(client, clock, failing, status):
    assert client.post(BIG, **failing).status_code == status
    assert client.post(BIG, json=REQUEST).status_code == 200


def test_server_error_response_gives_the_slot_back(client, clock, monkeypatch):
    def unavailable(*args):
        raise HTTPException(status_code=503, detail="Try later.")

    monkeypatch.setattr(routes, "compute_first_light", unavailable)
    statuses = [client.post(BIG, json=REQUEST).status_code for _ in range(2)]
    assert statuses == [503, 503]


def test_handler_that_raises_gives_the_slot_back(clock, monkeypatch):
    def broken(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "compute_first_light", broken)
    client = TestClient(app, raise_server_exceptions=False)
    statuses = [client.post(BIG, json=REQUEST).status_code for _ in range(2)]
    assert statuses == [500, 500]


def test_concurrent_pair_from_one_caller_gets_exactly_one_429(monkeypatch):
    real_compute = routes.compute_first_light
    entered = threading.Event()
    release = threading.Event()
    calls = []
    released_in_time = []

    def slow_first_call(*args):
        calls.append(args)
        if len(calls) == 1:
            entered.set()
            released_in_time.append(release.wait(WAIT_LIMIT_SECONDS))
        return real_compute(*args)

    monkeypatch.setattr(routes, "compute_first_light", slow_first_call)

    async def send_pair():
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            first = asyncio.create_task(async_client.post(BIG, json=REQUEST))
            try:
                await asyncio.to_thread(entered.wait, WAIT_LIMIT_SECONDS)
                second = await async_client.post(BIG, json=REQUEST)
            finally:
                release.set()
            return (await first).status_code, second.status_code

    statuses = asyncio.run(send_pair())

    # The second answer came while the first computation was still held,
    # so the two really overlapped.
    assert released_in_time == [True]
    assert statuses == (200, 429)


@pytest.mark.usefixtures("platform_header")
def test_refused_caller_is_answered_while_every_slot_is_held(monkeypatch):
    """The in-flight limit sits inside the rate limiter."""
    real_compute = routes.compute_first_light
    entered = threading.Semaphore(0)
    release = threading.Event()
    released_in_time = []

    def held(*args):
        entered.release()
        released_in_time.append(release.wait(WAIT_LIMIT_SECONDS))
        return real_compute(*args)

    monkeypatch.setattr(routes, "compute_first_light", held)
    callers = [f"203.0.113.{n}" for n in range(MAX_CONCURRENT_COMPUTATIONS)]

    async def fill_every_slot_then_ask_again():
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:

            def post(caller):
                return async_client.post(
                    BIG, json=REQUEST, headers={"True-Client-IP": caller}
                )

            holders = [asyncio.create_task(post(c)) for c in callers]
            try:
                for _ in callers:
                    await asyncio.to_thread(
                        entered.acquire, timeout=WAIT_LIMIT_SECONDS
                    )
                refused = await post(callers[0])
            finally:
                release.set()
            await asyncio.gather(*holders)
            return refused.status_code

    status = asyncio.run(fill_every_slot_then_ask_again())

    # The 429 came while every computation was still held.
    assert released_in_time == [True] * MAX_CONCURRENT_COMPUTATIONS
    assert status == 429


@pytest.mark.usefixtures("platform_header")
@pytest.mark.parametrize(
    ("newer_caller", "last_status"),
    [("203.0.113.9", 429), ("203.0.113.10", 200)],
    ids=["same-caller", "another-caller"],
)
def test_late_failure_gives_back_only_its_own_slot(
    clock, monkeypatch, newer_caller, last_status
):
    """A request failing after its window leaves a newer success in place.

    Another caller's request by then has cleared the failing one's
    record, which leaves it nothing to give back.
    """
    real_compute = routes.compute_first_light
    entered = threading.Event()
    fail = threading.Event()
    calls = []

    def slow_then_failing(*args):
        calls.append(args)
        if len(calls) > 1:
            return real_compute(*args)
        entered.set()
        fail.wait(WAIT_LIMIT_SECONDS)
        raise HTTPException(status_code=503, detail="Try later.")

    monkeypatch.setattr(routes, "compute_first_light", slow_then_failing)
    caller = "203.0.113.9"

    async def fail_after_a_newer_success():
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:

            def post(address):
                return async_client.post(
                    BIG, json=REQUEST, headers={"True-Client-IP": address}
                )

            slow = asyncio.create_task(post(caller))
            await asyncio.to_thread(entered.wait, WAIT_LIMIT_SECONDS)
            clock.now = START + 31
            newer = await post(newer_caller)
            fail.set()
            failed = await slow
            clock.now = START + 33
            again = await post(caller)
            return failed.status_code, newer.status_code, again.status_code

    assert asyncio.run(fail_after_a_newer_success()) == (
        503,
        200,
        last_status,
    )


def test_first_request_is_let_in_while_the_clock_reads_under_the_wait(
    client, clock
):
    """The monotonic clock can read a few seconds soon after a boot."""
    clock.now = 5.0
    assert client.post(BIG, json=REQUEST).status_code == 200
    clock.now = 12.0
    assert client.post(BIG, json=REQUEST).headers["retry-after"] == "23"


def test_get_health_never_takes_the_slot(client, clock):
    assert client.get("/health").status_code == 200
    assert client.post(BIG, json=REQUEST).status_code == 200
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "GET", "PUT"])
def test_other_methods_on_a_post_path_bypass_the_limit(client, clock, method):
    client.post(BIG, json=REQUEST)
    assert client.request(method, BIG).status_code == 405


def test_post_to_another_path_bypasses_the_limit(client, clock):
    client.post(BIG, json=REQUEST)
    assert client.post("/health").status_code == 405


def test_path_with_a_newline_after_it_shares_the_slot(client, clock):
    """Starlette sends ``<path>%0A`` to the same endpoint."""
    assert client.post(f"{BIG}%0A", json=REQUEST).status_code == 200
    assert client.post(BIG, json=REQUEST).status_code == 429


def test_path_under_a_server_root_path_is_limited(clock):
    """A server started with a root path puts it in front of each path."""
    behind_prefix = TestClient(app, root_path="/x")
    assert behind_prefix.post(f"/x{BIG}", json=REQUEST).status_code == 200
    assert behind_prefix.post(f"/x{BIG}", json=REQUEST).status_code == 429


def test_host_header_that_is_no_address_is_limited_like_any_other(
    client, clock
):
    """The scope's path is counted, whatever the Host header holds."""
    headers = {"Host": "[:0]"}
    assert client.post(BIG, json=REQUEST, headers=headers).status_code == 200
    assert client.post(BIG, json=REQUEST, headers=headers).status_code == 429


@pytest.mark.usefixtures("platform_header")
def test_different_callers_have_their_own_slots(client, clock):
    assert post_as(client, "203.0.113.9").status_code == 200
    assert post_as(client, "203.0.113.10").status_code == 200
    assert post_as(client, "203.0.113.9").status_code == 429


@pytest.mark.usefixtures("platform_header")
@pytest.mark.parametrize(
    ("first", "second", "status"),
    [
        ("2001:db8:1:2::1", "2001:db8:1:2::abcd", 429),
        ("2001:db8:1:3::1", "2001:db8:1:4::1", 200),
        ("203.0.113.9", "::ffff:203.0.113.9", 429),
    ],
    ids=["same-ipv6-64", "neighbouring-ipv6-64", "ipv4-mapped"],
)
def test_callers_are_limited_under_their_key(
    client, clock, first, second, status
):
    assert post_as(client, first).status_code == 200
    assert post_as(client, second).status_code == status


@pytest.mark.parametrize(
    ("address", "key"),
    [
        ("203.0.113.9", "203.0.113.9"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("2001:DB8:1:2::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:3::1", "2001:db8:1:3::/64"),
        ("::ffff:203.0.113.9", "203.0.113.9"),
        ("::1", "::/64"),
        ("testclient", "testclient"),
        ("unknown", "unknown"),
    ],
    ids=[
        "ipv4-as-it-is",
        "ipv6-to-its-64",
        "ipv6-top-of-the-64",
        "ipv6-upper-case",
        "ipv6-next-64",
        "ipv4-mapped-to-ipv4",
        "ipv6-loopback",
        "host-name-as-it-is",
        "unknown-as-it-is",
    ],
)
def test_caller_is_keyed_by_ipv4_address_or_ipv6_64(address, key):
    assert caller_key(address) == key


@pytest.mark.usefixtures("platform_header")
@pytest.mark.parametrize(
    "elapsed", [30.0, 86_400.0], ids=["exactly-the-window", "a-day-later"]
)
def test_callers_whose_wait_is_over_are_forgotten(client, clock, elapsed):
    post_as(client, "203.0.113.9")
    clock.now = START + elapsed
    post_as(client, "203.0.113.10")
    assert set(rate_limit._last_request) == {"203.0.113.10"}
