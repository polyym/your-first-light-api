"""Tests for capping the first-light requests in flight."""

import asyncio

import pytest
from fastapi import HTTPException

from first_light.app import app
from first_light.constants import MAX_CONCURRENT_COMPUTATIONS
from first_light.web.body_limit import BodySizeLimit
from first_light.web.in_flight import InFlightLimit
from first_light.web.routes import FIRST_LIGHT_PATHS

LIMITED = "/v1/big-endian-first-light"
SMALL_REQUEST = b'{"birthday": "1998-11-15", "categories": ["links"]}'
# Long enough for every request that is free to start to have started.
SETTLE_SECONDS = 0.05
# Ample for the app to answer small requests on a loaded machine. Only a
# request left waiting for a slot uses it up.
ANSWER_SECONDS = 10


class SlowSender:
    """An app whose response cannot be finished until it is let go."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.sent: list[str] = []
        self.let_go = asyncio.Event()

    async def __call__(self, scope, receive, send) -> None:
        self.started.append(scope["name"])
        await send({"type": "http.response.start", "status": 200})
        await self.let_go.wait()
        await send({"type": "http.response.body", "body": b"{}"})
        self.sent.append(scope["name"])


def scope(name: str, method: str = "POST", path: str = LIMITED) -> dict:
    return {"type": "http", "method": method, "path": path, "name": name}


async def receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


async def send(message: dict) -> None:
    pass


def test_third_request_waits_until_one_of_two_has_finished():
    async def scenario() -> tuple[list[str], list[str]]:
        inner = SlowSender()
        middleware = InFlightLimit(inner, paths={LIMITED}, limit=2)
        requests = [
            asyncio.create_task(middleware(scope(name), receive, send))
            for name in ("first", "second", "third")
        ]
        await asyncio.sleep(SETTLE_SECONDS)
        while_sending = list(inner.started)
        inner.let_go.set()
        await asyncio.gather(*requests)
        return while_sending, inner.started

    while_sending, started = asyncio.run(scenario())

    assert while_sending == ["first", "second"]
    assert started == ["first", "second", "third"]


def test_slot_is_held_until_a_streamed_response_ends():
    async def scenario() -> tuple[list[str], list[str]]:
        started: list[str] = []
        last_part = asyncio.Event()

        async def streaming(scope, receive, send) -> None:
            started.append(scope["name"])
            await send({"type": "http.response.start", "status": 200})
            await send(
                {"type": "http.response.body", "body": b"[", "more_body": True}
            )
            await last_part.wait()
            await send({"type": "http.response.body", "body": b"]"})

        middleware = InFlightLimit(streaming, paths={LIMITED}, limit=1)
        requests = [
            asyncio.create_task(middleware(scope(name), receive, send))
            for name in ("first", "second")
        ]
        await asyncio.sleep(SETTLE_SECONDS)
        while_streaming = list(started)
        last_part.set()
        await asyncio.gather(*requests)
        return while_streaming, started

    assert asyncio.run(scenario()) == (["first"], ["first", "second"])


def test_last_of_the_body_is_passed_on_after_the_app_has_returned():
    """So nothing the app holds of a response waits on its caller."""
    events: list[str] = []
    parts = [
        {"type": "http.response.start", "status": 200},
        {"type": "http.response.body", "body": b"{", "more_body": True},
        {"type": "http.response.body", "body": b"}"},
    ]

    async def responder(scope, receive, send) -> None:
        for part in parts:
            await send(part)
        events.append("returned")

    async def server_send(message: dict) -> None:
        events.append(message.get("body", b"start").decode())

    middleware = InFlightLimit(responder, paths={LIMITED}, limit=1)
    asyncio.run(middleware(scope("only"), receive, server_send))

    assert events == ["start", "{", "returned", "}"]


def test_what_follows_the_last_of_the_body_is_passed_on_after_it():
    """A streamed response ends in an empty part, and trailers may follow."""
    events: list[str] = []
    parts = [
        {"type": "http.response.start", "status": 200, "trailers": True},
        {"type": "http.response.body", "body": b"{}", "more_body": True},
        {"type": "http.response.body", "body": b""},
        {"type": "http.response.trailers", "headers": []},
    ]

    async def responder(scope, receive, send) -> None:
        for part in parts:
            await send(part)
        events.append("returned")

    async def server_send(message: dict) -> None:
        events.append(message["type"].removeprefix("http.response."))

    middleware = InFlightLimit(responder, paths={LIMITED}, limit=1)
    asyncio.run(middleware(scope("only"), receive, server_send))

    assert events == ["start", "body", "returned", "body", "trailers"]


def test_slot_is_free_while_the_last_of_the_body_is_being_sent():
    """That send may not return until the caller has read the response."""

    async def scenario() -> list[str]:
        read = asyncio.Event()
        started: list[str] = []

        async def responder(scope, receive, send) -> None:
            started.append(scope["name"])
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"{}"})

        async def unread(message: dict) -> None:
            if message["type"] == "http.response.body":
                await read.wait()

        middleware = InFlightLimit(responder, paths={LIMITED}, limit=1)
        requests = [
            asyncio.create_task(middleware(scope("unread"), receive, unread)),
            asyncio.create_task(middleware(scope("next"), receive, send)),
        ]
        await asyncio.sleep(SETTLE_SECONDS)
        while_unread = list(started)
        read.set()
        await asyncio.gather(*requests)
        return while_unread

    assert asyncio.run(scenario()) == ["unread", "next"]


def test_last_of_the_body_is_passed_on_when_the_app_then_fails():
    sent: list[dict] = []

    async def responder(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"{}"})
        raise RuntimeError("after the response")

    async def server_send(message: dict) -> None:
        sent.append(message)

    middleware = InFlightLimit(responder, paths={LIMITED}, limit=1)
    with pytest.raises(RuntimeError, match="after the response"):
        asyncio.run(middleware(scope("only"), receive, server_send))

    assert [message["type"] for message in sent] == [
        "http.response.start",
        "http.response.body",
    ]


def test_app_that_fails_gives_its_slot_back():
    async def scenario() -> list[str]:
        started: list[str] = []

        async def failing_once(scope, receive, send) -> None:
            started.append(scope["name"])
            if scope["name"] == "failing":
                raise RuntimeError("before any response")

        middleware = InFlightLimit(failing_once, paths={LIMITED}, limit=1)
        with pytest.raises(RuntimeError, match="before any response"):
            await middleware(scope("failing"), receive, send)
        await asyncio.wait_for(
            middleware(scope("next"), receive, send), ANSWER_SECONDS
        )
        return started

    assert asyncio.run(scenario()) == ["failing", "next"]


def replayed(uploaded: list[dict], reads: int) -> list[dict]:
    """What an app that reads ``reads`` messages gets of an upload."""

    async def scenario() -> list[dict]:
        pending = list(uploaded)
        seen: list[dict] = []

        async def upload() -> dict:
            return pending.pop(0)

        async def reader(scope, receive, send) -> None:
            for _ in range(reads):
                seen.append(await receive())

        middleware = InFlightLimit(reader, {LIMITED}, limit=1)
        await middleware(scope("reader"), upload, send)
        return seen

    return asyncio.run(scenario())


def test_other_requests_are_never_held_back():
    async def scenario() -> list[str]:
        inner = SlowSender()
        middleware = InFlightLimit(inner, paths={LIMITED}, limit=1)
        requests = [
            asyncio.create_task(middleware(scope(*args), receive, send))
            for args in (
                ("limited",),
                ("head", "HEAD"),
                ("other path", "POST", "/health"),
            )
        ]
        await asyncio.sleep(SETTLE_SECONDS)
        started = list(inner.started)
        inner.let_go.set()
        await asyncio.gather(*requests)
        return started

    assert asyncio.run(scenario()) == ["limited", "head", "other path"]


@pytest.mark.parametrize(
    "other",
    [
        {"type": "lifespan"},
        scope("put", "PUT"),
        scope("other path", "POST", "/health"),
    ],
    ids=["lifespan", "another-method", "another-path"],
)
def test_other_requests_are_passed_on_untouched(other):
    seen = []

    async def recorder(scope, receive, send) -> None:
        seen.append((scope, receive, send))

    middleware = InFlightLimit(recorder, {LIMITED}, limit=1)
    asyncio.run(middleware(other, receive, send))

    assert seen == [(other, receive, send)]


def test_path_the_router_serves_with_a_newline_after_it_is_limited():
    """Starlette sends ``<path>%0A`` to the same endpoint."""

    async def scenario() -> list[str]:
        inner = SlowSender()
        middleware = InFlightLimit(inner, paths={LIMITED}, limit=1)
        requests = [
            asyncio.create_task(
                middleware(scope(name, path=LIMITED + "\n"), receive, send)
            )
            for name in ("first", "second")
        ]
        await asyncio.sleep(SETTLE_SECONDS)
        started = list(inner.started)
        inner.let_go.set()
        await asyncio.gather(*requests)
        return started

    assert asyncio.run(scenario()) == ["first"]


def test_a_body_still_arriving_holds_no_slot():
    async def scenario() -> list[str]:
        inner = SlowSender()
        middleware = InFlightLimit(inner, paths={LIMITED}, limit=1)
        never = asyncio.Event()

        async def trickle() -> dict:
            await never.wait()
            return {"type": "http.request", "body": b"", "more_body": False}

        stalled = asyncio.create_task(
            middleware(scope("stalled"), trickle, send)
        )
        normal = asyncio.create_task(middleware(scope("normal"), receive, send))
        await asyncio.sleep(SETTLE_SECONDS)
        started = list(inner.started)
        inner.let_go.set()
        await normal
        stalled.cancel()
        return started

    assert asyncio.run(scenario()) == ["normal"]


def test_body_arrives_whole_and_in_order():
    chunks = [
        {"type": "http.request", "body": b'{"birth', "more_body": True},
        {"type": "http.request", "body": b'day": 1}', "more_body": False},
    ]

    async def scenario() -> bytes:
        pending = list(chunks)
        read = b""

        async def upload() -> dict:
            return pending.pop(0)

        async def app_reading_the_body(scope, receive, send) -> None:
            nonlocal read
            more = True
            while more:
                message = await receive()
                read += message["body"]
                more = message["more_body"]

        middleware = InFlightLimit(app_reading_the_body, {LIMITED}, limit=1)
        await middleware(scope("reader"), upload, send)
        return read

    assert asyncio.run(scenario()) == b'{"birthday": 1}'


def test_a_body_sent_a_byte_at_a_time_is_replayed_as_one_message():
    body = b'{"birthday": "1998-11-15"}'

    async def scenario() -> list[dict]:
        sent = 0
        seen: list[dict] = []

        async def bytewise() -> dict:
            nonlocal sent
            sent += 1
            return {
                "type": "http.request",
                "body": body[sent - 1 : sent],
                "more_body": sent < len(body),
            }

        async def reader(scope, receive, send) -> None:
            seen.append(await receive())

        middleware = InFlightLimit(reader, {LIMITED}, limit=1)
        await middleware(scope("bytewise"), bytewise, send)
        return seen

    assert asyncio.run(scenario()) == [
        {"type": "http.request", "body": body, "more_body": False}
    ]


def test_a_message_with_no_body_or_more_body_is_a_whole_empty_body():
    """ASGI lets a server leave both out."""
    assert replayed([{"type": "http.request"}], reads=1) == [
        {"type": "http.request", "body": b"", "more_body": False}
    ]


def test_a_caller_who_leaves_mid_body_reaches_the_app_as_gone():
    partial = {"type": "http.request", "body": b'{"birth', "more_body": True}
    gone = {"type": "http.disconnect"}

    assert replayed([partial, gone], reads=2) == [partial, gone]


def test_reads_after_the_body_go_to_the_server():
    """As when a response waits to hear that its caller has gone."""
    whole = {"type": "http.request", "body": b"{}", "more_body": False}
    gone = {"type": "http.disconnect"}

    assert replayed([whole, gone], reads=2) == [whole, gone]


def test_body_limit_refusal_reaches_the_app_where_it_reads():
    """The 413 then becomes JSON with CORS headers, as without the buffer."""
    reads = 0

    async def too_large_once() -> dict:
        # The body limit refuses a body sent in pieces on the read that
        # takes it over the limit, and may not refuse again.
        nonlocal reads
        reads += 1
        if reads > 1:
            return {"type": "http.disconnect"}
        raise HTTPException(status_code=413, detail="Request body too large.")

    async def app_reading_the_body(scope, receive, send) -> None:
        await receive()

    async def scenario() -> None:
        middleware = InFlightLimit(app_reading_the_body, {LIMITED}, limit=1)
        await middleware(scope("too large"), too_large_once, send)

    with pytest.raises(HTTPException) as refused:
        asyncio.run(scenario())
    assert refused.value.status_code == 413


def test_refused_or_cut_short_body_is_answered_without_a_slot():
    async def too_large() -> dict:
        raise HTTPException(status_code=413, detail="Request body too large.")

    async def gone() -> dict:
        return {"type": "http.disconnect"}

    async def scenario() -> list[str]:
        holder = SlowSender()
        answered: list[str] = []

        async def inner(scope, receive, send) -> None:
            if scope["name"] == "holder":
                await holder(scope, receive, send)
                return
            try:
                await receive()
            except HTTPException:
                pass
            answered.append(scope["name"])

        middleware = InFlightLimit(inner, paths={LIMITED}, limit=1)
        requests = [
            asyncio.create_task(middleware(scope(name), upload, send))
            for name, upload in (
                ("holder", receive),
                ("refused", too_large),
                ("gone", gone),
            )
        ]
        await asyncio.sleep(SETTLE_SECONDS)
        while_held = list(answered)
        holder.let_go.set()
        await asyncio.gather(*requests)
        return while_held

    assert asyncio.run(scenario()) == ["refused", "gone"]


def test_limit_holds_on_each_new_event_loop():
    """As on a test client, which starts a loop for each request."""
    middleware = InFlightLimit(SlowSender(), paths={LIMITED}, limit=1)

    async def scenario() -> list[str]:
        inner = SlowSender()
        middleware.app = inner
        requests = [
            asyncio.create_task(middleware(scope(name), receive, send))
            for name in ("first", "second")
        ]
        await asyncio.sleep(SETTLE_SECONDS)
        started = list(inner.started)
        inner.let_go.set()
        await asyncio.gather(*requests)
        return started

    assert [asyncio.run(scenario()) for _ in range(2)] == [["first"]] * 2


def test_body_limit_caps_the_body_the_in_flight_limit_buffers():
    """user_middleware lists the outermost first."""
    order = [m.cls for m in app.user_middleware]

    assert order.index(BodySizeLimit) < order.index(InFlightLimit)


def test_app_limits_every_first_light_endpoint():
    limits = [m for m in app.user_middleware if m.cls is InFlightLimit]

    assert len(limits) == 1
    assert limits[0].kwargs == {
        "paths": FIRST_LIGHT_PATHS,
        "limit": MAX_CONCURRENT_COMPUTATIONS,
    }


def test_callers_who_do_not_read_their_responses_hold_no_slot_in_the_app():
    """Starlette's function middleware waits for the server's last send.

    A server puts that send off for a caller who reads a large response
    slowly or not at all.
    """

    def http_scope(caller: str) -> dict:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": LIMITED,
            "raw_path": LIMITED.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "client": (caller, 50_000),
            "server": ("testserver", 80),
        }

    def upload():
        pending = [{"type": "http.request", "body": SMALL_REQUEST}]

        async def receive() -> dict:
            if pending:
                return pending.pop()
            # The caller stays connected.
            return await asyncio.Future()

        return receive

    async def scenario() -> list[int]:
        read = asyncio.Event()
        unread: list[dict] = []
        answered: list[int] = []

        async def not_reading(message: dict) -> None:
            last = not message.get("more_body", False)
            if message["type"] == "http.response.body" and last:
                unread.append(message)
                await read.wait()

        async def reading(message: dict) -> None:
            if message["type"] == "http.response.start":
                answered.append(message["status"])

        silent = [
            asyncio.create_task(
                app(http_scope(f"192.0.2.{caller}"), upload(), not_reading)
            )
            for caller in range(1, MAX_CONCURRENT_COMPUTATIONS + 1)
        ]
        try:
            async with asyncio.timeout(ANSWER_SECONDS):
                while len(unread) < MAX_CONCURRENT_COMPUTATIONS:
                    await asyncio.sleep(SETTLE_SECONDS)
                await app(http_scope("192.0.2.200"), upload(), reading)
        except TimeoutError:
            pass
        read.set()
        # Requests that never end must fail the test, not hold it up.
        async with asyncio.timeout(ANSWER_SECONDS):
            await asyncio.gather(*silent)
        return answered

    assert asyncio.run(scenario()) == [200]
