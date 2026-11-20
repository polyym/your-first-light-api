"""One log line for each request, with the caller and the time taken."""

import logging
import time
from collections.abc import Awaitable, Callable
from urllib.parse import quote

from fastapi import Request
from starlette.responses import Response

from first_light.web.client_ip import client_ip

logger = logging.getLogger(__name__)


async def log_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware that logs method, path, status, duration and caller.

    A request that raises is logged as a 500 before the error passes on
    to the 500 handler, so failures still appear with their duration.
    The path and the caller are percent-encoded: the server decodes a
    path before the app sees it, and a caller taken from a header is
    whatever was sent, so either could otherwise put spaces or control
    characters into the line.
    """
    start = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        logger.info(
            "%s %s %s %.0fms %s",
            request.method,
            # From the scope, the path as the server gives it: request.url
            # rebuilds it, dropping line breaks and escaping "?" and "#".
            _encoded(request.scope["path"]),
            status,
            (time.monotonic() - start) * 1000,
            _encoded(client_ip(request)),
        )


def _encoded(text: str) -> str:
    # The colons of an IPv6 address stay readable.
    return quote(text, safe="/:")
