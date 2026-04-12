FROM python:3.13-slim

# Prevent Python from writing .pyc files and enable
# unbuffered stdout/stderr for real-time container logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching).
# requirements.txt is the Docker cache key — keep it in sync
# with pyproject.toml [project.dependencies].
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and data
COPY src/ src/
COPY data/ data/

# Run as non-root user for security
RUN useradd --create-home appuser
USER appuser

# Warm the astropy ephemeris cache AS appuser so the cache
# lands in /home/appuser/.astropy/ where the app can read it.
RUN python -c "\
from astropy.coordinates import get_body; \
from astropy.time import Time; \
get_body('moon', Time.now()); \
print('Ephemeris cache warmed')"

EXPOSE 8000

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
