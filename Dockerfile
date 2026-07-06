FROM python:3.13-slim

# Prevent Python from writing .pyc files and enable
# unbuffered stdout/stderr for real-time container logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching).
# requirements.lock is fully pinned (generated with uv pip
# compile from pyproject.toml) so image builds are reproducible.
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy application code and data
COPY src/ src/
COPY data/ data/

# Run as non-root user for security
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Moon/Sun positions use astropy's built-in analytical ephemeris
# (ERFA); nothing is downloaded at runtime, so no cache warming
# is needed.
#
# X-Forwarded-For is handled in-app: set TRUSTED_PROXY_HOPS to
# the number of reverse proxies in front of the container
# (e.g. 1 behind a single proxy). The default of 0 ignores the
# header, which is correct when the port is exposed directly.
#
# Shell form so ${PORT} from the platform (e.g. Render) is
# honoured, defaulting to 8000 locally; exec replaces the shell
# so uvicorn is PID 1 and receives SIGTERM for graceful stops.
CMD exec uvicorn src.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
