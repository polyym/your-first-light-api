"""Caps how many first-light requests are computed and encoded at once."""

import asyncio
from collections.abc import Collection

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from first_light.web.routes import routed_path


class InFlightLimit:
    """ASGI middleware that lets at most ``limit`` POSTs to ``paths`` run.

    A slot is held from when the request body has arrived until the
    response is ready for the server, not only while it is computed: a
    large response stays in memory while it is encoded and compressed,
    so bounding the computation alone lets finished responses pile up.
    Requests beyond the limit wait their turn. A request whose body is
    refused or cut short takes no slot, since the app only answers its
    error.

    Sending is not covered: the server holds a response its caller has
    yet to read, outside this limit.
    """

    def __init__(
        self, app: ASGIApp, paths: Collection[str], limit: int
    ) -> None:
        self.app = app
        self.paths = paths
        self.limit = limit
        self._slots: asyncio.Semaphore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Reads a limited request's body, then runs it in a slot."""
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or routed_path(scope) not in self.paths
        ):
            await self.app(scope, receive, send)
            return

        # The body is read before a slot is taken, so a caller who sends
        # it slowly holds only their own connection. It is kept as one
        # message, so a body sent a byte at a time costs no more than its
        # size. The body limit outside caps it; its 413 is raised where
        # the app reads the body, as it would be without this buffer.
        body = bytearray()
        complete = False
        ending: Message | None = None
        refusal: HTTPException | None = None
        try:
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    ending = message
                    break
                body += message.get("body", b"")
                if not message.get("more_body", False):
                    complete = True
                    break
        except HTTPException as e:
            refusal = e
        messages: list[Message] = []
        if body or complete:
            messages.append(
                {
                    "type": "http.request",
                    "body": bytes(body),
                    "more_body": not complete,
                }
            )
        if ending is not None:
            messages.append(ending)

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            if refusal is not None:
                raise refusal
            return await receive()

        if not complete:
            # Refused or cut short: the app has only an error to answer.
            await self.app(scope, replay, send)
            return

        # The last part of the body is kept back until the app has
        # returned and its slot is free. Starlette's function middleware
        # outside (the rate limiter and the access log, see app.py) does
        # not return from sending that part until the server has sent
        # the whole response, which takes as long as the caller takes to
        # read it. Sent from inside the app, it would keep the slot, and
        # all the app still holds of the response, for that long. The
        # response therefore ends only once the app has returned: a route
        # behind this limit that works on after its last send, or waits
        # there for its caller to go, holds its own response up.
        kept_back: list[Message] = []

        async def send_all_but_last(message: Message) -> None:
            last = message["type"] == "http.response.body" and not message.get(
                "more_body", False
            )
            # What follows the last part, such as trailers, waits behind
            # it: passed on at once, it would reach the server first.
            if last or kept_back:
                kept_back.append(message)
            else:
                await send(message)

        try:
            async with self._slots_for_running_loop():
                await self.app(scope, replay, send_all_but_last)
        finally:
            # Also for an app that fails after its response, whose caller
            # would have had the whole of it without this.
            for message in kept_back:
                await send(message)

    def _slots_for_running_loop(self) -> asyncio.Semaphore:
        # A semaphore belongs to one event loop. The server runs a single
        # loop for its lifetime; a test client starts a new one each time.
        loop = asyncio.get_running_loop()
        if self._slots is None or self._loop is not loop:
            self._slots = asyncio.Semaphore(self.limit)
            self._loop = loop
        return self._slots
