"""Allows each caller one successful POST every ``RATE_LIMIT_SECONDS``.

The record of callers lives in this process, so it does not hold
across several workers or replicas.
"""

import ipaddress
import math
import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from first_light.constants import IPV6_CALLER_PREFIX, RATE_LIMIT_SECONDS
from first_light.web.client_ip import client_ip
from first_light.web.routes import FIRST_LIGHT_PATHS, routed_path

# Caller to the time of its last request that counts, on the monotonic
# clock, so that a change to the system clock cannot stretch a wait.
_last_request: dict[str, float] = {}


async def rate_limit(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware that answers 429 to a caller inside their wait.

    A request that fails (4xx or 5xx) gives its slot back, so that
    correcting a mistyped date does not cost a wait.
    """
    if (
        request.method != "POST"
        or routed_path(request.scope) not in FIRST_LIGHT_PATHS
    ):
        return await call_next(request)

    now = time.monotonic()
    for known, recorded in list(_last_request.items()):
        if now - recorded >= RATE_LIMIT_SECONDS:
            del _last_request[known]

    caller = caller_key(client_ip(request))
    last = _last_request.get(caller)
    if last is not None and now - last < RATE_LIMIT_SECONDS:
        wait = RATE_LIMIT_SECONDS - (now - last)
        # Rounded up, so a client that waits the time stated is let in.
        # Clients read the first number in the sentence: keep it first.
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    f"Rate limited. Please wait {math.ceil(wait * 10) / 10} "
                    f"seconds before trying again."
                ),
            },
            headers={"Retry-After": str(math.ceil(wait))},
        )

    # Recorded before the request runs, so that concurrent requests from
    # one caller cannot all pass the check at once.
    _last_request[caller] = now
    try:
        response = await call_next(request)
    except Exception:
        _refund(caller, now)
        raise
    if response.status_code >= 400:
        _refund(caller, now)
    return response


def _refund(caller: str, recorded: float) -> None:
    """Gives back the slot this request took, and no later one."""
    # A request still running when its window ends loses its record, and
    # a newer request from the same caller may have taken its place.
    if _last_request.get(caller) == recorded:
        del _last_request[caller]


def caller_key(address: str) -> str:
    """Gives the key a caller is limited under.

    One IPv6 subscriber holds a whole /64 and can pick any address in
    it, so IPv6 callers are limited by network. An IPv4 address written
    as IPv6 counts as the IPv4 address. Anything that is not an address
    is used as it is.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        network = ipaddress.IPv6Network((ip, IPV6_CALLER_PREFIX), strict=False)
        return str(network)
    return str(ip)
