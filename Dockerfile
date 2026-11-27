# Both images are pinned by digest, and Dependabot proposes updates to
# each. uv comes in as a stage of its own, since Dependabot reads only
# FROM lines.
FROM ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f AS uv

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

# Settings for uv, which runs only while the image is built: as build
# arguments they reach that step and stay out of the image. Dependencies
# are compiled to bytecode as they are installed. The app writes none at
# run time, so a cold start would otherwise compile every import, which
# nearly doubles it on a small instance.
ARG UV_NO_CACHE=1
ARG UV_COMPILE_BYTECODE=1
ARG UV_PYTHON_DOWNLOADS=never

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so a code change reuses this layer. uv is mounted
# from its stage for this step alone, so the image carries no binary
# that nothing runs. The project itself is not installed: it runs from
# src/ beside data/, which it finds relative to its own files.
COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --locked --no-dev --no-install-project

COPY src/ src/
COPY data/ data/

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Through a shell so that a platform's PORT is honoured, with exec so
# that uvicorn is PID 1 and stops on SIGTERM once the requests it has
# open have ended. Proxy headers are read by the app (web/client_ip.py).
# uvicorn is left at its default, which takes them from a loopback peer
# alone. The app logs each request itself, so uvicorn's access log would
# only repeat it.
CMD ["/bin/sh", "-c", "exec uvicorn first_light.app:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
