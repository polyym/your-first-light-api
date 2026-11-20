"""The API's routes: an index, a health check and three POST endpoints.

The three POST endpoints differ only in the date format they accept.
"""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from starlette.types import Scope

from first_light.constants import (
    API_DESCRIPTION,
    API_TITLE,
    API_VERSION,
    MAX_BODY_BYTES,
    MAX_CONCURRENT_COMPUTATIONS,
    RATE_LIMIT_SECONDS,
)
from first_light.facts.catalogues import (
    DATA_MANIFEST,
    NEARBY_STARS,
    SOLAR_ECLIPSE_DATES,
)
from first_light.facts.compute import compute_first_light
from first_light.models import (
    ALL_CATEGORIES,
    BigEndianRequest,
    ErrorResponse,
    FirstLightResponse,
    HealthResponse,
    LittleEndianRequest,
    MiddleEndianRequest,
    RateLimitResponse,
)
from first_light.web.body_limit import too_large_detail
from first_light.web.date_formats import (
    parse_big_endian,
    parse_little_endian,
    parse_middle_endian,
)
from first_light.web.errors import UNEXPECTED_ERROR_DETAIL

router = APIRouter()

# Computations run off the event loop on a pool of their own, as large as
# the number of requests web/in_flight.py lets in at once.
_computations = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_COMPUTATIONS, thread_name_prefix="compute"
)

_INDEX_PATH = "/"
_HEALTH_PATH = "/health"
# The app serves its interactive docs here (app.py).
DOCS_PATH = "/docs"
_BIG_ENDIAN_PATH = "/v1/big-endian-first-light"
_MIDDLE_ENDIAN_PATH = "/v1/middle-endian-first-light"
_LITTLE_ENDIAN_PATH = "/v1/little-endian-first-light"
FIRST_LIGHT_PATHS = frozenset(
    {_BIG_ENDIAN_PATH, _MIDDLE_ENDIAN_PATH, _LITTLE_ENDIAN_PATH}
)


def routed_path(scope: Scope) -> str:
    """Gives the path the router matches a request by.

    The limits must count a request as the path it is served under,
    which is not always the path it arrived with. A server started with
    a root path puts that in front of every path, and the router takes
    it off again before matching. Starlette's route patterns end in
    ``$``, which also matches before a trailing newline, so a path with
    ``%0A`` after it reaches the same endpoint. The path is read from
    the scope, as the router reads it: ``request.url`` rebuilds it,
    dropping line breaks and escaping ``?`` and ``#``.
    """
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if root_path and path.startswith(f"{root_path}/"):
        path = path.removeprefix(root_path)
    return path.removesuffix("\n")


def _example(detail: str) -> dict[str, Any]:
    """The OpenAPI example body of an error with this detail."""
    return {"application/json": {"example": {"detail": detail}}}


# The error responses of the POST endpoints, for the OpenAPI schema.
_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "model": ErrorResponse,
        "description": "A body that cannot be decoded, such as invalid UTF-8.",
        # FastAPI's own wording.
        "content": _example("There was an error parsing the body"),
    },
    413: {
        "model": ErrorResponse,
        "description": f"A body larger than {MAX_BODY_BYTES // 1024} KB.",
        "content": _example(too_large_detail(MAX_BODY_BYTES)),
    },
    422: {
        "model": ErrorResponse,
        "description": (
            "A date that does not parse, a birthday that is not before "
            "as_of (today when it is left out), or another invalid field."
        ),
    },
    429: {
        "model": RateLimitResponse,
        "description": (
            f"Rate limited: one successful request every "
            f"{RATE_LIMIT_SECONDS} s for each caller."
        ),
        "headers": {
            "Retry-After": {
                "description": "The wait in whole seconds.",
                "schema": {"type": "integer"},
            },
        },
    },
    500: {
        "model": ErrorResponse,
        "description": "An unexpected server error.",
        "content": _example(UNEXPECTED_ERROR_DETAIL),
    },
}


# Uptime monitors often probe with HEAD, which FastAPI does not add to a
# GET route. Each of the two paths has a twin, kept out of the schema,
# that answers both methods: the router builds a 405 from the first route
# registered for a path, which is the twin, so its Allow header names GET
# and HEAD. The GET route above the twin is the one the schema documents.
@router.get(_INDEX_PATH)
@router.api_route(_INDEX_PATH, methods=["GET", "HEAD"], include_in_schema=False)
def index() -> dict[str, object]:
    """Names the API, its version and its endpoints."""
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "description": API_DESCRIPTION,
        "docs_url": DOCS_PATH,
        "health_url": _HEALTH_PATH,
        "endpoints": sorted(FIRST_LIGHT_PATHS),
    }


@router.get(
    _HEALTH_PATH,
    responses={
        200: {"model": HealthResponse},
        503: {"model": HealthResponse, "description": "A catalogue is empty."},
    },
)
@router.api_route(
    _HEALTH_PATH, methods=["GET", "HEAD"], include_in_schema=False
)
def health() -> JSONResponse:
    """Says whether the catalogues are loaded.

    Not rate limited. An empty catalogue gives a 503, so that a platform
    health check, which reads only the status, takes the server out of
    service.
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
            name: info.get("updated") for name, info in manifest_files.items()
        }
    return JSONResponse(payload, status_code=200 if ok else 503)


@router.post(
    _BIG_ENDIAN_PATH,
    summary="Birthday as YYYY-MM-DD",
    response_model_exclude_none=True,
    responses=_ERROR_RESPONSES,
)
async def big_endian_first_light(req: BigEndianRequest) -> FirstLightResponse:
    """Computes the facts for a birthday written as YYYY-MM-DD."""
    return await _first_light(req, parse_big_endian)


@router.post(
    _MIDDLE_ENDIAN_PATH,
    summary="Birthday as MM/DD/YYYY",
    response_model_exclude_none=True,
    responses=_ERROR_RESPONSES,
)
async def middle_endian_first_light(
    req: MiddleEndianRequest,
) -> FirstLightResponse:
    """Computes the facts for a birthday written as MM/DD/YYYY."""
    return await _first_light(req, parse_middle_endian)


@router.post(
    _LITTLE_ENDIAN_PATH,
    summary="Birthday as DD/MM/YYYY",
    response_model_exclude_none=True,
    responses=_ERROR_RESPONSES,
)
async def little_endian_first_light(
    req: LittleEndianRequest,
) -> FirstLightResponse:
    """Computes the facts for a birthday written as DD/MM/YYYY."""
    return await _first_light(req, parse_little_endian)


async def _first_light(
    req: BigEndianRequest | MiddleEndianRequest | LittleEndianRequest,
    parse: Callable[[str], date],
) -> FirstLightResponse:
    """Parses the request's dates and computes the response off the loop.

    Raises:
        HTTPException: 422 for a date that does not parse or a birthday
            that is not before as_of.
    """
    try:
        birth = parse(req.birthday)
        # Left out, as_of is the UTC date, which can differ from the
        # caller's own date around midnight. An empty one is an error.
        as_of = (
            datetime.now(UTC).date() if req.as_of is None else parse(req.as_of)
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    if birth >= as_of:
        raise HTTPException(
            status_code=422, detail="Birthday must be in the past."
        )
    categories = (
        set(req.categories) if req.categories is not None else ALL_CATEGORIES
    )
    return await asyncio.get_running_loop().run_in_executor(
        _computations,
        compute_first_light,
        birth,
        as_of,
        categories,
        req.star_limit,
    )
