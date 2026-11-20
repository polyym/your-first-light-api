"""Tests for refusing request bodies over the size limit."""

import asyncio
import json

import pytest
from fastapi import HTTPException

from first_light.web.body_limit import BodySizeLimit, too_large_detail

LIMIT = 2048
BIG = "/v1/big-endian-first-light"
REQUEST = {
    "birthday": "1998-11-15",
    "as_of": "2026-11-18",
    "categories": ["links"],
}


class Upload:
    """Feeds a body to the middleware in chunks and records what it read."""

    def __init__(self, chunks, content_length=None):
        self.chunks = list(chunks)
        self.headers = [(b"content-type", b"application/json")]
        if content_length is not None:
            self.headers.append((b"content-length", content_length))
        self.pulled = 0
        self.delivered = b""

    async def receive(self):
        chunk = self.chunks[self.pulled]
        self.pulled += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": self.pulled < len(self.chunks),
        }

    async def app(self, scope, receive, send):
        more = True
        while more:
            message = await receive()
            self.delivered += message["body"]
            more = message["more_body"]

    def run(self):
        async def send(message):
            pass

        middleware = BodySizeLimit(self.app, max_bytes=LIMIT)
        scope = {"type": "http", "headers": self.headers}
        asyncio.run(middleware(scope, self.receive, send))


def refused(upload):
    with pytest.raises(HTTPException) as excinfo:
        upload.run()
    return excinfo.value


def test_declared_length_over_the_limit_is_refused_before_reading():
    upload = Upload([b"x" * (LIMIT + 1)], content_length=b"2049")
    error = refused(upload)
    assert (error.status_code, error.detail) == (
        413,
        "Request body too large; the limit is 2 KB.",
    )
    assert upload.pulled == 0


def test_non_numeric_content_length_is_refused_before_reading():
    upload = Upload([b"{}"], content_length=b"ten")
    assert refused(upload).status_code == 413
    assert upload.pulled == 0


@pytest.mark.parametrize(
    ("chunks", "content_length"),
    [
        ([b"x" * LIMIT], b"2048"),
        ([b"x" * 1024, b"x" * 1024], None),
        ([b"x" * 1000], b"1000"),
        ([b""], None),
    ],
    ids=["declared-exactly", "chunked-exactly", "under", "empty"],
)
def test_body_up_to_the_limit_is_passed_on_whole(chunks, content_length):
    upload = Upload(chunks, content_length)
    upload.run()
    assert upload.delivered == b"".join(chunks)


@pytest.mark.parametrize(
    ("chunks", "content_length", "pulled"),
    [
        ([b"x" * 1024, b"x" * 1025], None, 2),
        ([b"x" * (LIMIT + 1)], b"10", 1),
    ],
    ids=["chunked-one-over", "longer-than-declared"],
)
def test_body_one_byte_over_the_limit_is_refused_as_it_arrives(
    chunks, content_length, pulled
):
    upload = Upload(chunks, content_length)
    error = refused(upload)
    assert (error.status_code, error.detail) == (
        413,
        "Request body too large; the limit is 2 KB.",
    )
    assert upload.pulled == pulled


def test_detail_gives_the_limit_in_whole_binary_kilobytes():
    assert too_large_detail(1024 * 1024) == (
        "Request body too large; the limit is 1024 KB."
    )


def test_a_caller_leaving_is_passed_on_to_the_app():
    gone = {"type": "http.disconnect"}
    seen = []

    async def app(scope, receive, send):
        seen.append(await receive())

    async def receive():
        return gone

    async def send(message):
        pass

    middleware = BodySizeLimit(app, max_bytes=LIMIT)
    asyncio.run(middleware({"type": "http", "headers": []}, receive, send))
    assert seen == [gone]


def test_non_http_scopes_pass_through_untouched():
    seen = []

    async def app(scope, receive, send):
        seen.append((scope, receive, send))

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message):
        pass

    lifespan = {"type": "lifespan"}
    middleware = BodySizeLimit(app, max_bytes=LIMIT)
    asyncio.run(middleware(lifespan, receive, send))
    assert seen == [(lifespan, receive, send)]


@pytest.mark.parametrize(
    ("size", "status"),
    [(64 * 1024, 200), (64 * 1024 + 1, 413)],
    ids=["exactly-64-kb", "one-byte-over"],
)
def test_app_accepts_a_body_of_up_to_64_kb(client, size, status):
    body = json.dumps(REQUEST).encode()
    padded = body + b" " * (size - len(body))
    response = client.post(
        BIG, content=padded, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == status


def test_app_answers_413_with_cors(client):
    response = client.post(
        BIG,
        content=b'{"birthday": "' + b"x" * 70_000 + b'"}',
        headers={
            "Content-Type": "application/json",
            "Origin": "https://example.org",
        },
    )
    assert response.status_code == 413
    assert response.json() == {
        "detail": "Request body too large; the limit is 64 KB."
    }
    assert response.headers["access-control-allow-origin"] == "*"


def test_413_gives_the_rate_limit_slot_back(client):
    too_large = client.post(
        BIG,
        content=b" " * (64 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert too_large.status_code == 413
    assert client.post(BIG, json=REQUEST).status_code == 200
