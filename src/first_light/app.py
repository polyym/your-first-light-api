"""The ASGI application: middleware, error handlers and routes.

Serve it with ``uvicorn first_light.app:app``.
"""

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from first_light.constants import (
    API_DESCRIPTION,
    API_TITLE,
    API_VERSION,
    GZIP_MINIMUM_BYTES,
    MAX_BODY_BYTES,
    MAX_CONCURRENT_COMPUTATIONS,
)
from first_light.web.access_log import log_request
from first_light.web.body_limit import BodySizeLimit
from first_light.web.errors import (
    handle_unexpected_error,
    handle_validation_error,
)
from first_light.web.in_flight import InFlightLimit
from first_light.web.rate_limit import rate_limit
from first_light.web.routes import DOCS_PATH, FIRST_LIGHT_PATHS, router

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url=DOCS_PATH,
)

# Starlette wraps each middleware around the ones added before it, so
# they are added from the innermost out. The in-flight limit sits inside
# the rate limiter, so a refused caller never waits for a slot, and
# inside the body limit, which caps the body it reads before taking one.
# The body limit sits inside the rate limiter, so its 413 gives the
# caller's slot back. CORS sits outside both, so their 429 and 413 carry
# its headers; only the 500 handler runs outside CORS (see
# web/errors.py). The access log is outermost, so it also records the
# preflights that CORS answers itself.
app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_BYTES)
app.add_middleware(
    InFlightLimit, paths=FIRST_LIGHT_PATHS, limit=MAX_CONCURRENT_COMPUTATIONS
)
app.add_middleware(BodySizeLimit, max_bytes=MAX_BODY_BYTES)
app.middleware("http")(rate_limit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Browsers hide response headers that are neither safelisted nor
    # exposed, and clients may want to read the wait from this one.
    expose_headers=["Retry-After"],
)
app.middleware("http")(log_request)

app.exception_handler(Exception)(handle_unexpected_error)
app.exception_handler(RequestValidationError)(handle_validation_error)
app.include_router(router)
