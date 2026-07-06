"""Your First Light — FastAPI REST layer.

Thin HTTP wrapper around the astronomy computation engine.
Provides versioned POST endpoints for three date formats, per-IP
rate limiting, request logging, and structured error handling.
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from src.compute import (
    DATA_MANIFEST,
    NEARBY_STARS,
    SOLAR_ECLIPSE_DATES,
    compute_first_light,
)
from src.models import (
    ALL_CATEGORIES,
    BigEndianRequest,
    ErrorResponse,
    FirstLightResponse,
    LittleEndianRequest,
    MiddleEndianRequest,
    RateLimitResponse,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Your First Light",
    description="Post your birthday. Discover your cosmic reach.",
    version="1.1.1",
)

# NOTE: CORSMiddleware is registered at the bottom of this module,
# after the rate-limiting and logging middleware, so that it wraps
# them and 429 responses also carry CORS headers.
app.add_middleware(GZipMiddleware, minimum_size=1000)


# -------------------------------------------------------------------
# Global exception handlers
# -------------------------------------------------------------------
def _cors_headers(request: Request) -> dict[str, str]:
    """CORS headers for responses produced outside the middleware.

    The 500 handler runs in Starlette's outermost
    ``ServerErrorMiddleware``, so its response never passes
    through ``CORSMiddleware``.  Because the API allows all
    origins without credentials, a static wildcard is correct.

    Args:
        request: The incoming HTTP request.

    Returns:
        CORS headers when the request is cross-origin,
        otherwise an empty dict.
    """
    if "origin" in request.headers:
        return {"Access-Control-Allow-Origin": "*"}
    return {}


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Return structured JSON for any unhandled error.

    Args:
        request: The incoming HTTP request that triggered the error.
        exc: The unhandled exception.

    Returns:
        A 500 JSON response with a generic error message.
    """
    logger.exception(
        "Unhandled error on %s", request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred."},
        headers=_cors_headers(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Normalise Pydantic validation errors to the documented shape.

    FastAPI's default 422 body carries ``detail`` as a list of
    error objects, which contradicts the published
    ``ErrorResponse`` schema (a plain string).  This handler
    flattens the first validation error into a single
    human-readable message so every 422 has the same shape.

    Args:
        request: The incoming HTTP request.
        exc: The validation error raised by Pydantic.

    Returns:
        A 422 JSON response with ``detail`` as a string.
    """
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = ".".join(
            str(part) for part in first.get("loc", ())
            if part != "body"
        )
        msg = first.get("msg", "Invalid request.")
        detail = f"{loc}: {msg}" if loc else msg
    else:
        detail = "Invalid request."
    return JSONResponse(
        status_code=422,
        content={"detail": detail},
    )


# -------------------------------------------------------------------
# Client IP extraction (proxy-aware, opt-in)
# -------------------------------------------------------------------
# Name of a request header that the hosting platform's edge sets
# to the verified client address as a single value, e.g.
# "True-Client-IP" on Render (which fronts every service with
# Cloudflare), "CF-Connecting-IP" behind Cloudflare directly, or
# "Fly-Client-IP" on Fly.io.  Takes precedence over the hop-count
# logic below because platform chains can contain a variable
# number of internal hops.  Leave empty when no such header
# exists.
CLIENT_IP_HEADER = os.environ.get(
    "CLIENT_IP_HEADER", "",
).strip()

# Number of trusted reverse proxies between the client and this
# app.  0 (the default) means the port is directly exposed and
# X-Forwarded-For is entirely attacker-supplied, so it is ignored
# and the direct peer address is used.  Behind a conventional
# proxy chain, set TRUSTED_PROXY_HOPS to the number of proxy hops
# so the entry appended by the first trusted proxy is selected.
TRUSTED_PROXY_HOPS = int(
    os.environ.get("TRUSTED_PROXY_HOPS", "0"),
)


def _get_client_ip(request: Request) -> str:
    """Extract the client IP used for rate limiting and logging.

    Resolution order:

    1. ``CLIENT_IP_HEADER``, when configured and present: the
       platform edge sets this to the verified caller address,
       which is reliable even when the platform's own proxy
       chain has a variable number of hops (as on Render).
    2. ``TRUSTED_PROXY_HOPS`` set to N > 0: each of the N
       trusted proxies appends the address of the peer it
       accepted, so the real client is the Nth entry from the
       right of ``X-Forwarded-For``.  Anything further left is
       client-supplied and trivially spoofable, so it is never
       consulted.
    3. Otherwise the direct peer address; forwarding headers on
       a directly exposed port are attacker-controlled.

    Args:
        request: The incoming HTTP request.

    Returns:
        Client IP string, or ``"unknown"`` when unavailable.
    """
    if CLIENT_IP_HEADER:
        value = request.headers.get(CLIENT_IP_HEADER)
        if value:
            # Platform identity headers carry a single address;
            # take the first token defensively regardless.
            return value.split(",")[0].strip()
    hops = TRUSTED_PROXY_HOPS
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            entries = [
                e.strip() for e in forwarded.split(",")
                if e.strip()
            ]
            if len(entries) >= hops:
                return entries[-hops]
            if entries:
                # Shorter chain than configured: the request
                # bypassed some proxies; use the outermost entry.
                return entries[0]
    if request.client:
        return request.client.host
    return "unknown"


# -------------------------------------------------------------------
# Rate limiter — 1 request per 30 seconds per IP
#
# NOTE: In-memory, per-process only. Will not synchronise across
# multiple uvicorn workers or deployment replicas. For multi-worker
# deployments, replace with a shared store such as Redis.
# -------------------------------------------------------------------
_rate_limit: dict[str, float] = {}
RATE_LIMIT_SECONDS = 30

_RATE_LIMITED_PATHS = {
    "/v1/big-endian-first-light",
    "/v1/middle-endian-first-light",
    "/v1/little-endian-first-light",
}


@app.middleware("http")
async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Enforce per-IP rate limiting on POST endpoints.

    Allows one request per ``RATE_LIMIT_SECONDS`` per client IP
    on rate-limited paths.  Stale entries are evicted on each
    invocation to prevent unbounded memory growth.  A request
    that fails downstream (4xx/5xx, e.g. a date-format mistake)
    releases its slot again, so a corrected retry is not
    punished with a 429.

    Args:
        request: The incoming HTTP request.
        call_next: ASGI middleware chain continuation.

    Returns:
        A 429 JSON response if rate-limited, otherwise the
        downstream response.
    """
    if (
        request.url.path in _RATE_LIMITED_PATHS
        and request.method == "POST"
    ):
        now = time.time()
        # Evict stale entries to prevent unbounded growth
        stale = [
            ip for ip, ts in _rate_limit.items()
            if now - ts >= RATE_LIMIT_SECONDS
        ]
        for ip in stale:
            del _rate_limit[ip]

        client_ip = _get_client_ip(request)
        last = _rate_limit.get(client_ip, 0)
        if now - last < RATE_LIMIT_SECONDS:
            wait = round(
                RATE_LIMIT_SECONDS - (now - last), 1,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limited. Please wait "
                        f"{wait} seconds before trying "
                        f"again."
                    ),
                },
                headers={
                    "Retry-After": str(int(wait) + 1),
                },
            )
        # Record before awaiting so concurrent requests from the
        # same IP cannot all pass the check at once, then refund
        # the slot if this request turns out to be an error.
        _rate_limit[client_ip] = now
        try:
            response = await call_next(request)
        except Exception:
            _rate_limit.pop(client_ip, None)
            raise
        if response.status_code >= 400:
            _rate_limit.pop(client_ip, None)
        return response
    return await call_next(request)


# -------------------------------------------------------------------
# Request logging
# -------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Log every request with method, path, status, and duration.

    Requests that raise are logged as 500 before the exception
    propagates to the outermost error middleware, so failed
    requests still appear in the access log with their duration
    and client IP.

    Args:
        request: The incoming HTTP request.
        call_next: ASGI middleware chain continuation.

    Returns:
        The downstream response, unmodified.
    """
    start = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s %s %.0fms %s",
            request.method,
            request.url.path,
            status,
            elapsed_ms,
            _get_client_ip(request),
        )


# -------------------------------------------------------------------
# CORS — registered last so it is the OUTERMOST user middleware.
# Starlette wraps middleware in reverse registration order, so
# adding CORS here means 429s from the rate limiter (and every
# other middleware response) also carry CORS headers.  Responses
# from the 500 handler run outside all user middleware and get
# their CORS headers from ``_cors_headers`` instead.
# -------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------
# Date parsers
# -------------------------------------------------------------------
def _parse(s: str, fmt: str, label: str) -> date:
    """Parse a date string or raise ``ValueError``.

    Args:
        s: Raw date string from the request.
        fmt: ``strptime`` format code.
        label: Human-readable format name for errors.

    Returns:
        A ``date`` object.

    Raises:
        ValueError: If *s* does not match *fmt*.
    """
    try:
        return datetime.strptime(s, fmt).date()
    except ValueError:
        raise ValueError(
            f"Invalid date: {s!r}. Expected {label}.",
        ) from None


def parse_big_endian(s: str) -> date:
    """Parse ``YYYY-MM-DD``."""
    return _parse(s, "%Y-%m-%d", "YYYY-MM-DD")


def parse_middle_endian(s: str) -> date:
    """Parse ``MM/DD/YYYY``."""
    return _parse(s, "%m/%d/%Y", "MM/DD/YYYY")


def parse_little_endian(s: str) -> date:
    """Parse ``DD/MM/YYYY``."""
    return _parse(s, "%d/%m/%Y", "DD/MM/YYYY")


# -------------------------------------------------------------------
# Root index (root level — no version prefix, not rate limited)
# -------------------------------------------------------------------
@app.get("/")
def index() -> dict[str, object]:
    """Small JSON index so the base URL is not a bare 404.

    Returns:
        A dict with the API name, version, and useful paths.
    """
    return {
        "name": app.title,
        "version": app.version,
        "description": app.description,
        "docs_url": "/docs",
        "health_url": "/health",
        "endpoints": sorted(_RATE_LIMITED_PATHS),
    }


# -------------------------------------------------------------------
# Health (root level — no version prefix)
# -------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, object]:
    """Readiness probe — verifies data files are loaded.

    Returns:
        A dict with ``status`` (``"ok"`` or ``"degraded"``),
        ``stars_loaded`` and ``eclipses_loaded`` counts, and,
        when data/manifest.json exists, a ``data_updated``
        mapping of data file to the date it last changed.
    """
    stars = len(NEARBY_STARS)
    eclipses = len(SOLAR_ECLIPSE_DATES)
    ok = stars > 0 and eclipses > 0
    payload: dict[str, object] = {
        "status": "ok" if ok else "degraded",
        "stars_loaded": stars,
        "eclipses_loaded": eclipses,
    }
    manifest_files = DATA_MANIFEST.get("files", {})
    if manifest_files:
        payload["data_updated"] = {
            name: info.get("updated")
            for name, info in manifest_files.items()
        }
    return payload


# -------------------------------------------------------------------
# Shared request handler
# -------------------------------------------------------------------
async def _handle(
    birthday_str: str,
    as_of_str: str | None,
    categories: Sequence[str] | None,
    star_limit: int,
    parser: Callable[[str], date],
) -> FirstLightResponse:
    """Shared request handler for all three date formats.

    Args:
        birthday_str: Raw birthday string from the request.
        as_of_str: Optional reference date string.
        categories: Optional category filter list.
        star_limit: Max stars to return in the list.
        parser: Date-parsing function to apply.

    Returns:
        A computed ``FirstLightResponse``.

    Raises:
        HTTPException: On invalid dates or future birthdays.
    """
    try:
        birth = parser(birthday_str)
    except ValueError as e:
        raise HTTPException(
            status_code=422, detail=str(e),
        )

    # The default reference date is the current UTC date, which
    # can differ from the caller's local date around midnight.
    ref = datetime.now(timezone.utc).date()
    if as_of_str:
        try:
            ref = parser(as_of_str)
        except ValueError as e:
            raise HTTPException(
                status_code=422, detail=str(e),
            )

    if birth >= ref:
        raise HTTPException(
            status_code=422,
            detail="Birthday must be in the past.",
        )

    # categories is either None (all) or a non-empty list; the
    # request models reject an explicit empty list with a 422.
    cats = (
        set(categories) if categories is not None
        else ALL_CATEGORIES
    )
    return await asyncio.to_thread(
        compute_first_light, birth, ref, cats, star_limit,
    )


# -------------------------------------------------------------------
# Versioned endpoints
# -------------------------------------------------------------------
router = APIRouter(prefix="/v1")

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {
        "model": ErrorResponse,
        "description": (
            "Invalid or future date, or invalid request "
            "fields (all 422s use this shape)."
        ),
    },
    429: {
        "model": RateLimitResponse,
        "description": (
            "Rate limited (1 request per 30 s per IP)."
        ),
    },
}


@router.post(
    "/big-endian-first-light",
    response_model=FirstLightResponse,
    response_model_exclude_none=True,
    responses=_ERROR_RESPONSES,
)
async def big_endian_first_light(
    req: BigEndianRequest,
) -> FirstLightResponse:
    """Accept a birthday in YYYY-MM-DD (big-endian) format.

    Args:
        req: Request body with ``birthday`` in YYYY-MM-DD format
            and optional filtering parameters.

    Returns:
        Computed astronomy facts for the given birthday.
    """
    return await _handle(
        req.birthday, req.as_of, req.categories,
        req.star_limit, parse_big_endian,
    )


@router.post(
    "/middle-endian-first-light",
    response_model=FirstLightResponse,
    response_model_exclude_none=True,
    responses=_ERROR_RESPONSES,
)
async def middle_endian_first_light(
    req: MiddleEndianRequest,
) -> FirstLightResponse:
    """Accept a birthday in MM/DD/YYYY (middle-endian) format.

    Args:
        req: Request body with ``birthday`` in MM/DD/YYYY format
            and optional filtering parameters.

    Returns:
        Computed astronomy facts for the given birthday.
    """
    return await _handle(
        req.birthday, req.as_of, req.categories,
        req.star_limit, parse_middle_endian,
    )


@router.post(
    "/little-endian-first-light",
    response_model=FirstLightResponse,
    response_model_exclude_none=True,
    responses=_ERROR_RESPONSES,
)
async def little_endian_first_light(
    req: LittleEndianRequest,
) -> FirstLightResponse:
    """Accept a birthday in DD/MM/YYYY (little-endian) format.

    Args:
        req: Request body with ``birthday`` in DD/MM/YYYY format
            and optional filtering parameters.

    Returns:
        Computed astronomy facts for the given birthday.
    """
    return await _handle(
        req.birthday, req.as_of, req.categories,
        req.star_limit, parse_little_endian,
    )


app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    # Proxy headers are handled by _get_client_ip via the
    # TRUSTED_PROXY_HOPS setting, not by uvicorn: trusting
    # X-Forwarded-For from any peer would let clients spoof
    # their rate-limit identity on a directly exposed port.
    uvicorn.run(
        "src.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
