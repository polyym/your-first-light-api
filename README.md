# Your First Light - API

An astronomy API that calculates your cosmic reach from your birthday.

When you were born, light began radiating outward from that point in space. This API calculates how far that expanding sphere has travelled -- which stars it has reached, what the Moon looked like that night, how many eclipses have occurred, how far the Voyager probes have moved, and more.

## Endpoints

Each endpoint accepts a different date format to avoid day/month ambiguity (is `01/02/2003` January 2nd or February 1st?). All three return the same response.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/v1/big-endian-first-light` | Birthday as `YYYY-MM-DD` |
| `POST` | `/v1/middle-endian-first-light` | Birthday as `MM/DD/YYYY` |
| `POST` | `/v1/little-endian-first-light` | Birthday as `DD/MM/YYYY` |

## Request

```json
{
  "birthday": "2002-10-14",
  "as_of": "2026-04-11",
  "categories": ["moon", "stars", "voyagers"],
  "star_limit": 100
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `birthday` | Yes | Date of birth in the endpoint's format |
| `as_of` | No | Reference date (defaults to today). Uses the same format as `birthday` |
| `categories` | No | Categories to include (defaults to all). See [Response categories](#response-categories) |
| `star_limit` | No | Max stars in the `stars` list (1--50,000, default 500). Counts and `next_star` are always complete. When truncated, `stars_remaining` describes the omitted stars |

## Response

Only requested categories appear in the response. `birthday` and `as_of` are always present (ISO 8601).

Here is a response for `{"birthday": "2002-10-14", "categories": ["time_alive", "links"]}`:

```json
{
  "birthday": "2002-10-14",
  "as_of": "2026-04-11",
  "age_years": 23.49,
  "age_days": 8580,
  "age_hours": 205920,
  "age_minutes": 12355200,
  "age_seconds": 741312000,
  "earth_rotations": 8603.49,
  "leap_years_lived_through": 6,
  "nasa_apod_url": "https://apod.nasa.gov/apod/ap021014.html"
}
```

The full response schema with all 14 categories is available at `/docs` when the server is running.

### Response categories

- **time_alive** -- age in years/days/hours/minutes/seconds, sidereal earth rotations, leap years
- **moon** -- phase at midnight UTC (name, illumination, moon age in days), full moons since birth
- **light_sphere** -- radius/diameter in light-years/km/AU, volume, surface area, Milky Way and observable universe coverage
- **stars** -- reached count, naked-eye count, birthday star, full star list with distance/spectral type/magnitude/exoplanets/RA/Dec coordinates (J2000), next star with arrival date
- **exoplanets** -- total known exoplanets within sphere, estimated habitable worlds
- **star_classification** -- reached stars grouped by spectral class
- **planetary_ages** -- age on Mercury through Pluto
- **body_stats** -- heartbeats, breaths, blinks, infrared photons emitted, net thermal radiation
- **cosmic_journey** -- distance around the Sun, galactic orbit distance/degrees, Great Attractor movement, universe expansion
- **scale_comparisons** -- light sphere as trips to Moon/Sun/Pluto, crossing times, Earths by volume
- **universe_perspective** -- age as percentage of universe's age
- **voyagers** -- Voyager 1 and 2 distance since birth in km and AU
- **eclipses** -- solar, lunar, total eclipse counts since birth
- **links** -- NASA APOD URL for birthday

## Errors

All errors return JSON with a `detail` field.

| Status | Meaning | Example |
|--------|---------|---------|
| `422` | Invalid or future date | `{"detail": "Invalid date: 'bad'. Expected YYYY-MM-DD."}` |
| `429` | Rate limited | `{"detail": "Rate limited. Please wait 25.3 seconds before trying again."}` |
| `500` | Server error | `{"detail": "An unexpected error occurred."}` |

`429` responses include a `Retry-After` header (seconds).

## Rate limiting

One request per 30 seconds per IP across all POST endpoints. `GET /health` is not rate limited.

The rate limiter is in-memory and per-process. It does not synchronise across multiple workers or deployment replicas.

## Local development

### With venv

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn src.app:app --reload
```

Or install as an editable package with dev dependencies:

```bash
pip install -e ".[dev]"
pytest
```

Interactive API docs at `http://localhost:8000/docs`.

### With Docker

```bash
docker compose up
```

Or build and run manually:

```bash
docker build -t your-first-light .
docker run -p 8000:8000 your-first-light
```

The API will be available at `http://localhost:8000`.

## Deploy to Render

1. Push this repo to GitHub
2. Connect to Render and deploy -- `render.yaml` handles the config
3. Or set start command manually: `uvicorn src.app:app --host 0.0.0.0 --port $PORT`

The free tier spins down after inactivity. The first request after a cold start takes a few extra seconds while the ephemeris cache initialises.

## Project structure

```
src/
  constants.py   -- physical/astronomical constants
  models.py      -- Pydantic request/response schemas
  compute.py     -- astronomy computation engine (no FastAPI)
  app.py         -- FastAPI REST layer
data/
  stars.json     -- nearby star catalogue (auto-generated)
  eclipses.json  -- solar/lunar eclipse dates (auto-generated)
tests/
  conftest.py           -- shared fixtures
  test_endpoints.py     -- endpoint validation and edge cases
  test_compute.py       -- astronomy computation engine tests
  test_rate_limiting.py -- rate limiting and IP extraction
  test_categories.py    -- individual response categories
  test_parsers.py       -- date parsing functions
  test_e2e.py           -- end-to-end request lifecycle
tools/
  update_data.py              -- single entry point to refresh all data
  updaters/update_stars.py    -- star catalogue updater (HIPPARCOS, Gliese, Gaia, NASA Exoplanet Archive)
  updaters/update_eclipses.py -- eclipse catalogue updater (NASA Five Millennium Catalog)
```

## Updating data

Refresh all data files from upstream sources with a single command:

```bash
python tools/update_data.py
git add data/
git commit -m "Refresh data catalogues"
```

Missing dependencies (like `astroquery`) are installed automatically on first run. You can also update individually:

```bash
python tools/update_data.py stars     # stars only
python tools/update_data.py eclipses  # eclipses only
```

| Data file | Source | Script |
|-----------|--------|--------|
| `data/stars.json` | HIPPARCOS, Gliese, Gaia DR3, NASA Exoplanet Archive | `tools/updaters/update_stars.py` |
| `data/eclipses.json` | NASA Five Millennium Catalog of Eclipses | `tools/updaters/update_eclipses.py` |

Both scripts auto-fix data quality issues (deduplication, spectral type normalisation, coordinate validation) and validate before writing. If validation fails the script exits with code 1 without modifying the data file.

## Data sources

| Data | Source |
|------|--------|
| Star positions and properties | HIPPARCOS (ESA), Gliese Catalogue of Nearby Stars, Gaia DR3 (ESA) |
| Exoplanet counts | NASA Exoplanet Archive |
| Eclipse dates | NASA Five Millennium Catalog of Eclipses (GSFC) |
| Moon phase and ephemeris | Astropy + JPL DE440s |
| Voyager distances | JPL Horizons System |
| Physical constants | Astropy (CODATA/IAU) |

## AI usage

Claude Sonnet 4.6 Extended (Anthropic) wrote all of the tests and assisted with some of the documentation.

## Python version

Requires Python 3.13+. See `.python-version` and `pyproject.toml`.
