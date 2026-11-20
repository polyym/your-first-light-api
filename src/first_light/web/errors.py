"""Error handlers: every error body is ``{"detail": "<plain text>"}``."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

UNEXPECTED_ERROR_DETAIL = "An unexpected error occurred."


async def handle_unexpected_error(
    request: Request, exc: Exception
) -> JSONResponse:
    """Answers a plain 500 for an unhandled error.

    The server logs the traceback itself, after this handler, and the
    access log records the request. This handler runs in Starlette's
    outermost ``ServerErrorMiddleware``, outside the CORS middleware, so
    it adds that middleware's headers itself: the allow-origin header
    for a request that names an origin, and ``Vary: Origin`` on every
    answer, since the answer depends on that header. The API allows
    every origin without credentials, so a wildcard is right.
    """
    headers = {"Vary": "Origin"}
    if "origin" in request.headers:
        headers["Access-Control-Allow-Origin"] = "*"
    return JSONResponse(
        status_code=500,
        content={"detail": UNEXPECTED_ERROR_DETAIL},
        headers=headers,
    )


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Answers a 422 whose detail is one sentence, not a list.

    FastAPI's own 422 lists error objects, which does not match the
    documented string. The first error is enough to correct a request.
    """
    errors = exc.errors()
    if not errors:
        return _unprocessable("Invalid request.")
    first = errors[0]
    kind = first.get("type")
    location = tuple(first.get("loc", ()))
    if kind == "json_invalid":
        return _unprocessable("Request body is not valid JSON.")
    if location == ("body",) and kind == "missing":
        return _unprocessable("Request body is required.")
    if location == ("body",) and kind in ("model_attributes_type", "dict_type"):
        # FastAPI reads a body as JSON only when it is declared as JSON.
        if not _is_json(request.headers.get("content-type", "")):
            return _unprocessable("Content-Type must be application/json.")
        return _unprocessable("Request body must be a JSON object.")
    field = ".".join(str(part) for part in location if part != "body")
    message = first.get("msg", "Invalid request.")
    return _unprocessable(f"{field}: {message}" if field else message)


def _is_json(content_type: str) -> bool:
    media_type = content_type.split(";")[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _unprocessable(detail: str) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": detail})
