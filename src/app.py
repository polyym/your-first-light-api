"""Your First Light — FastAPI REST layer.

Thin HTTP wrapper around the astronomy computation engine.
Provides versioned POST endpoints for three date formats, per-IP
rate limiting, request logging, and structured error handling.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import date, datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from src.compute import (
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
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# -------------------------------------------------------------------
# Global exception handler
# -------------------------------------------------------------------
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
    )


# -------------------------------------------------------------------
# Client IP extraction (proxy-aware)
# -------------------------------------------------------------------
def _get_client_ip(request: Request) -> str:
    """Extract the real client IP from the request.

    Uses the **rightmost** ``X-Forwarded-For`` entry — the one
    added by our own reverse proxy (Render, CloudFlare, etc.).
    The leftmost entry is client-supplied and trivially spoofable,
    so it must never be trusted for rate limiting.

    Args:
        request: The incoming HTTP request.

    Returns:
        Client IP string, or ``"unknown"`` when unavailable.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2
        # Rightmost = added by our trusted edge proxy.
        return forwarded.split(",")[-1].strip()
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
    call_next: Callable[[Request], Response],
) -> Response:
    """Enforce per-IP rate limiting on POST endpoints.

    Allows one request per ``RATE_LIMIT_SECONDS`` per client IP
    on rate-limited paths.  Stale entries are evicted on each
    invocation to prevent unbounded memory growth.

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
        _rate_limit[client_ip] = now
    return await call_next(request)


# -------------------------------------------------------------------
# Request logging
# -------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Response],
) -> Response:
    """Log every request with method, path, status, and duration.

    Args:
        request: The incoming HTTP request.
        call_next: ASGI middleware chain continuation.

    Returns:
        The downstream response, unmodified.
    """
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s %s %.0fms %s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        _get_client_ip(request),
    )
    return response


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
# Health (root level — no version prefix)
# -------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, object]:
    """Readiness probe — verifies data files are loaded.

    Returns:
        A dict with ``status`` (``"ok"`` or ``"degraded"``),
        ``stars_loaded``, and ``eclipses_loaded`` counts.
    """
    stars = len(NEARBY_STARS)
    eclipses = len(SOLAR_ECLIPSE_DATES)
    ok = stars > 0 and eclipses > 0
    return {
        "status": "ok" if ok else "degraded",
        "stars_loaded": stars,
        "eclipses_loaded": eclipses,
    }


# -------------------------------------------------------------------
# Shared request handler
# -------------------------------------------------------------------
async def _handle(
    birthday_str: str,
    as_of_str: str | None,
    categories: list[str] | None,
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

    ref = date.today()
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

    cats = set(categories) if categories else ALL_CATEGORIES
    return await asyncio.to_thread(
        compute_first_light, birth, ref, cats, star_limit,
    )


# -------------------------------------------------------------------
# Versioned endpoints
# -------------------------------------------------------------------
router = APIRouter(prefix="/v1")

_ERROR_RESPONSES = {
    422: {
        "model": ErrorResponse,
        "description": "Invalid or future date.",
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

    uvicorn.run(
        "src.app:app",
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
