# Your First Light - API

An astronomy API that calculates your cosmic reach from your birthday.

When you were born, light began radiating outward from that point in space. This API calculates how far that expanding sphere has travelled -- which stars it has reached, what the Moon looked like that night, how many eclipses have occurred, how far the Voyager probes have moved, and more.

## Endpoints

Each endpoint accepts a different date format to avoid day/month ambiguity (is `01/02/2003` January 2nd or February 1st?). All three return the same response.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | JSON index (name, version, endpoint paths) |
| `GET` | `/health` | Health check, data counts and freshness |
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
| `as_of` | No | Reference date (defaults to the current UTC date). Uses the same format as `birthday` |
| `categories` | No | Categories to include (defaults to all). Must be non-empty when provided; an explicit `[]` is rejected with a 422. See [Response categories](#response-categories) |
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

The full response schema with all 15 categories is available at `/docs` when the server is running.

### Response categories

- **time_alive** -- age in years/days/hours/minutes/seconds, sidereal earth rotations, leap years
- **moon** -- phase at midnight UTC (name, illumination, moon age in days), full moons since birth, next full moon date
- **light_sphere** -- radius/diameter in light-years/km/AU, volume, surface area, Milky Way and observable universe coverage
- **stars** -- reached count, naked-eye count, stars reached in the past year, birthday star, full star list with distance/spectral type/magnitude/exoplanets/RA/Dec coordinates (J2000), next star with arrival date
- **exoplanets** -- total known exoplanets within sphere, estimated habitable worlds
- **star_classification** -- reached stars grouped by spectral class
- **planetary_ages** -- age on Mercury through Pluto
- **body_stats** -- heartbeats, breaths, blinks, infrared photons emitted, net thermal radiation
- **cosmic_journey** -- distance around the Sun, galactic orbit distance/degrees, Great Attractor movement, universe expansion
- **scale_comparisons** -- light sphere as trips to Moon/Sun/Pluto, crossing times, Earths by volume
- **universe_perspective** -- age as percentage of universe's age
- **voyagers** -- Voyager 1 and 2 distance since birth in km and AU
- **eclipses** -- solar, lunar, total eclipse counts since birth, next solar and lunar eclipse dates
- **links** -- NASA APOD URL for birthday
- **sun_constellation** -- the IAU constellation the Sun was actually in on the birthday (one of 13, including Ophiuchus) versus the traditional star sign, and whether they agree

## Errors

All errors return JSON with a `detail` field that is always a plain string, including request-validation errors (a custom handler flattens FastAPI's default list-of-objects shape).

| Status | Meaning | Example |
|--------|---------|---------|
| `422` | Invalid date, future date, or invalid request fields | `{"detail": "Invalid date: 'bad'. Expected YYYY-MM-DD."}` |
| `429` | Rate limited | `{"detail": "Rate limited. Please wait 25.3 seconds before trying again."}` |
| `500` | Server error | `{"detail": "An unexpected error occurred."}` |

`429` responses include a `Retry-After` header (seconds). All responses, including `429` and `500`, carry CORS headers so browser clients can read them.

## Rate limiting

One request per 30 seconds per IP across all POST endpoints. `GET /`, `GET /health`, and requests that fail (4xx/5xx) do not consume the slot, so correcting a mistyped date does not cost a 30-second wait.

The rate limiter is in-memory and per-process. It does not synchronise across multiple workers or deployment replicas.

### Client IP extraction behind a proxy

By default the limiter keys on the direct peer address and ignores forwarding headers, because on a directly exposed port they are entirely attacker-supplied (varying `X-Forwarded-For` would mint a fresh rate-limit bucket per request). Two settings adapt this to a deployment:

- `CLIENT_IP_HEADER`: the name of a header your platform's edge sets to the verified caller address as a single value. Render fronts every service with Cloudflare and provides `True-Client-IP`, so `render.yaml` sets `CLIENT_IP_HEADER=True-Client-IP`. This takes precedence, because platform chains (Cloudflare plus internal hops on Render) contain a variable number of entries and no fixed hop count is reliable.
- `TRUSTED_PROXY_HOPS`: for a conventional reverse-proxy chain without such a header, set the number of trusted hops; the limiter uses the `X-Forwarded-For` entry appended by the first trusted proxy and never anything further left.

## Local development

### With venv

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
pip install -e ".[dev]"
uvicorn src.app:app --reload
```

Run the checks the CI runs:

```bash
ruff check .
mypy
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

The free tier spins down after inactivity, so the first request after a cold start takes a few extra seconds while the process starts and the catalogues load.

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
  manifest.json  -- data provenance: sources, entry counts, last-changed dates
tests/
  conftest.py           -- shared fixtures
  test_endpoints.py     -- endpoint validation and edge cases
  test_compute.py       -- astronomy computation engine tests
  test_rate_limiting.py -- rate limiting and IP extraction
  test_errors_cors.py   -- CORS on error paths, 500 logging, 422 shape
  test_categories.py    -- individual response categories
  test_parsers.py       -- date parsing functions
  test_updaters.py      -- data updater merge/validation logic (offline)
  test_e2e.py           -- end-to-end request lifecycle
tools/
  update_data.py              -- single entry point to refresh all data
  updaters/update_stars.py    -- star catalogue updater (HIPPARCOS, Gliese, Gaia, NASA Exoplanet Archive)
  updaters/update_eclipses.py -- eclipse catalogue updater (NASA Five Millennium Catalog)
.github/workflows/
  ci.yml          -- lint and tests on pushes and pull requests
  update-data.yml -- scheduled monthly data refresh via pull request
requirements.lock -- fully pinned dependency set used by the Docker image
```

## Updating data

Data updates are automated. A scheduled GitHub Actions workflow (`.github/workflows/update-data.yml`) runs monthly: it regenerates both catalogues from their upstream sources, validates them, runs the full test suite against the refreshed data, and opens a pull request only when the data actually changed. Review the diff and merge; nothing lands on `main` without a human looking at it. The workflow can also be triggered manually from the Actions tab.

To refresh locally instead, install the catalogue extra and run the same entry point:

```bash
pip install -e ".[catalogue]"
python tools/update_data.py           # everything
python tools/update_data.py stars     # stars only
python tools/update_data.py eclipses  # eclipses only
```

The script never installs packages itself; if `astroquery` is missing it prints the install command and exits.

| Data file | Source | Script |
|-----------|--------|--------|
| `data/stars.json` | HIPPARCOS, Gliese, Gaia DR3, NASA Exoplanet Archive | `tools/updaters/update_stars.py` |
| `data/eclipses.json` | NASA Five Millennium Catalog of Eclipses | `tools/updaters/update_eclipses.py` |

Both updaters auto-fix data quality issues (cross-catalogue deduplication with distance-scaled tolerances, spectral type normalisation, Gaia G to V magnitude conversion) and validate before writing, including a positional-duplicate check that fails the run if the same star appears twice under different designations. Degraded fetches also fail the run: every upstream source must return at least half of its expected row count, and eclipse coverage is checked per year, so a partially failed refresh can never produce a plausible-looking but incomplete data file. Writes are atomic (temp file plus rename), so an interrupted run can never leave a truncated catalogue, and files are only rewritten when their content actually changed. `data/manifest.json` records the source, entry count, and last-changed date for each file, which `/health` reports as `data_updated`.

## Data sources

| Data | Source |
|------|--------|
| Star positions and properties | HIPPARCOS (ESA), Gliese Catalogue of Nearby Stars, Gaia DR3 (ESA) |
| Exoplanet counts | NASA Exoplanet Archive |
| Eclipse dates | NASA Five Millennium Catalog of Eclipses (GSFC) |
| Moon phase and ephemeris | Astropy built-in analytical ephemeris (ERFA); its error is far below the response rounding |
| Voyager distances | JPL Horizons System |
| Physical constants | Astropy (CODATA/IAU) |

## AI usage

Claude Sonnet 4.6 Extended (Anthropic) wrote all of the tests for v1.0 and assisted with some of the documentation. Claude Opus 4.8 (Anthropic) implemented the v1.1 changes, working from a human-reviewed code review; see CHANGELOG.md.

## Python version

Requires Python 3.13+. See `.python-version` and `pyproject.toml`.
