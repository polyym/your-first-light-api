"""Refuses request bodies over a size limit with a 413."""

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def too_large_detail(max_bytes: int) -> str:
    """The 413 detail for a body over ``max_bytes``."""
    return f"Request body too large; the limit is {max_bytes // 1024} KB."


class BodySizeLimit:
    """ASGI middleware that refuses a request body over ``max_bytes``.

    A declared ``Content-Length`` is checked before anything is read,
    and a body sent without one (chunked) is counted as it arrives. The
    413 is raised from the receive channel as an ``HTTPException``, so
    FastAPI gives it the same JSON shape as every other error.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Passes a request on with its body counted as it is read."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared: int | None = None
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = self.max_bytes + 1
                break

        detail = too_large_detail(self.max_bytes)
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            if declared is not None and declared > self.max_bytes:
                raise HTTPException(status_code=413, detail=detail)
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail=detail)
            return message

        await self.app(scope, limited_receive, send)
