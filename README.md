# Your First Light - API

An astronomy API that calculates your cosmic reach from your birthday.

When you were born, light began radiating outward from that point in space. This API calculates how far that expanding sphere has travelled: which stars it has reached, what the Moon looked like that night, how many eclipses have occurred, how far the Voyager probes have moved, and more.

## Endpoints

Each endpoint accepts a different date format to avoid day/month ambiguity (is `01/02/2003` 1 February or 2 January?). All three return the same response.

| Method | Path | Description |
|--------|------|-------------|
| `GET`, `HEAD` | `/` | JSON index: name, version and endpoint paths |
| `GET`, `HEAD` | `/health` | Whether the catalogues are loaded, with counts and when the data last changed |
| `POST` | `/v1/big-endian-first-light` | Birthday as `YYYY-MM-DD` |
| `POST` | `/v1/middle-endian-first-light` | Birthday as `MM/DD/YYYY` |
| `POST` | `/v1/little-endian-first-light` | Birthday as `DD/MM/YYYY` |

The full schema, with field descriptions, is at `/docs` when the server is running.

## Request

```json
{
  "birthday": "1998-11-15",
  "as_of": "2026-04-11",
  "categories": ["moon", "stars", "voyagers"],
  "star_limit": 100
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `birthday` | Yes | Date of birth in the endpoint's format, from year 0001 to 9999. Every date is read in the Gregorian calendar, also before its adoption in 1582 |
| `as_of` | No | The date to measure up to, in the same format. Leave it out for the current UTC date |
| `categories` | No | Categories to include; leave it out for all 15. An empty list is rejected. See [Response categories](#response-categories) |
| `star_limit` | No | The most stars to list, nearest first (1 to 50,000, default 500). Counts and `next_star` always cover the whole catalogue, and `stars_remaining` says how many were left out |

## Response

Only requested categories appear. `birthday` and `as_of` are always present, as `YYYY-MM-DD`. Within a requested category, a field with no value is left out: `birthday_star` when no star's distance is within 2 light-years of the age, `next_star` once every star is reached, `stars_remaining` when the list is complete, a star's `magnitude_band` when it is unknown, and the eclipses' `next_solar_eclipse`, `next_lunar_eclipse` and `coverage_note` when they do not apply.

The response to `{"birthday": "1998-11-15", "as_of": "2026-04-11", "categories": ["time_alive", "links"]}`:

```json
{
  "birthday": "1998-11-15",
  "as_of": "2026-04-11",
  "age_years": 27.4,
  "age_days": 10009,
  "age_hours": 240216,
  "age_minutes": 14412960,
  "age_seconds": 864777606,
  "earth_rotations": 10036.4,
  "leap_years_lived_through": 7,
  "nasa_apod_url": "https://apod.nasa.gov/apod/ap981115.html"
}
```

### Response categories

- **time_alive**: age in years, days, hours, minutes and seconds, sidereal Earth rotations, and 29 Februaries lived through. `age_seconds` is physically elapsed time, so it includes the leap seconds inserted during the lifetime (six in the example above) and differs from `age_days` x 86,400 by the leap seconds in between: up to 27 more for a birthday since 1972 or 37 for an earlier one, or one fewer for a short span across UTC's backward steps of 1961 and 1968. Hours and minutes derive from it.
- **moon**: the phase at midnight UTC on the birthday (name, illumination, age in the cycle), the full moons since, and the date of the next. Full moons are the instants the Moon is 180 degrees from the Sun in ecliptic longitude.
- **light_sphere**: radius in light-years, km and AU, diameter, volume, surface area, the share of the Milky Way and the observable universe, and the speed of light.
- **stars**: stars reached, those visible to the naked eye and those reached in the past year, the birthday star, the list of stars with distance, spectral type and class, magnitude, exoplanets and J2000 coordinates, and the next star with its arrival date.
- **exoplanets**: known exoplanets of the stars reached, and an estimate of potentially habitable ones.
- **star_classification**: the stars reached, grouped by class. A class label always ends in its letter in brackets, such as `Red dwarf (M)` or `Orange giant (K)`; a star with no recorded type is `Unknown`.
- **planetary_ages**: age on Mercury through Pluto.
- **body_stats**: heartbeats, breaths, blinks, infrared photons emitted and net thermal radiation, for an average adult.
- **cosmic_journey**: distance travelled round the Sun and round the galaxy, movement towards the Great Attractor, and the expansion of the universe.
- **scale_comparisons**: the light sphere as trips to the Moon, the Sun and Pluto, crossing times by car, jet and Voyager 1, Earths by volume, and the distance travelled round the galaxy.
- **universe_perspective**: age as a percentage of the universe's age.
- **voyagers**: how far Voyager 1 and 2 have flown since the birthday, in km and AU.
- **eclipses**: the solar and lunar eclipses since the birthday and their sum, and the next of each, from NASA's catalogue for 1900 to 2100. A lifetime that reaches outside those years gets a note saying which part the counts cover.
- **links**: NASA's Astronomy Picture of the Day for the birthday, or APOD's front page for a day before it began on 16 June 1995 or after 15 June 2095, when its two-digit page names would repeat.
- **sun_constellation**: the IAU constellation the Sun was actually in on the birthday, one of the 13 on its path with Ophiuchus included, against the traditional star sign, and whether they agree. Thousands of years ahead, precession also brings Cetus and Orion.

## Errors

Every error the API itself answers is JSON with a `detail` field holding one line of plain text, never a list.

| Status | Meaning | Example |
|--------|---------|---------|
| `400` | A body that cannot be decoded, such as invalid UTF-8 | `{"detail": "There was an error parsing the body"}` |
| `413` | A body over 64 KB | `{"detail": "Request body too large; the limit is 64 KB."}` |
| `422` | A date that does not parse, a birthday that is not before `as_of` (today when it is left out), or another invalid field | `{"detail": "Invalid date: 'bad'. Expected YYYY-MM-DD."}` |
| `429` | Rate limited | `{"detail": "Rate limited. Please wait 25.3 seconds before trying again."}` |
| `500` | Server error | `{"detail": "An unexpected error occurred."}` |

A `429` carries a `Retry-After` header in whole seconds, and its detail gives the wait as its first number, rounded up to a tenth. Every response, errors included, carries CORS headers, and `Retry-After` is exposed to browsers.

## Rate limiting

Each caller may make one successful request every 30 seconds, across all three POST endpoints. A request that fails (4xx or 5xx) does not use the slot, so correcting a mistyped date costs no wait, and `/` and `/health` are never limited. An IPv6 caller is limited by its /64 network, since one subscriber holds the whole of it.

The limiter lives in the server process, so it does not hold across several workers or replicas.

## Running locally

The project uses [uv](https://docs.astral.sh/uv/), which installs Python 3.13 and the exact versions in `uv.lock`:

```bash
uv sync
uv run uvicorn first_light.app:app --app-dir src --reload
```

The API is then at `http://localhost:8000`, with interactive docs at `/docs`. This request returns the response shown under [Response](#response):

```bash
curl -X POST http://localhost:8000/v1/big-endian-first-light \
  -H "Content-Type: application/json" \
  -d '{"birthday": "1998-11-15", "as_of": "2026-04-11", "categories": ["time_alive", "links"]}'
```

The checks that run on every push to `main` and every pull request:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

With Docker instead:

```bash
docker compose up
```

## Deployment

Render runs the Docker image and deploys each push to `main`. `render.yaml` describes the service as a Render Blueprint; a service created in Render's dashboard takes its settings from there instead, with the Docker runtime, no Docker command (the image's own `CMD` runs) and `/health` as its health check. On the free plan the service sleeps when idle, so the first request after a pause waits while the process starts and loads the catalogues.

The repository needs one setting that cannot be written in a workflow file: "Allow GitHub Actions to create and approve pull requests", under Settings, Actions, General, Workflow permissions. Without it the data refresh pushes its branch and then fails.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8000` | The port the image listens on |
| `CLIENT_IP_HEADER` | `True-Client-IP` on Render, otherwise none | A header the platform's edge sets to the verified caller address, such as `CF-Connecting-IP` or `Fly-Client-IP`. It takes precedence over `TRUSTED_PROXY_HOPS` |
| `TRUSTED_PROXY_HOPS` | `0` | The number of reverse proxies in front of the app, for a conventional proxy chain with no such header. The caller is then the entry that the first trusted proxy added to `X-Forwarded-For` |

With neither set, the limiter reads no forwarding header, which on a port exposed directly is whatever the caller wants it to be, and uses the peer address the server reports. uvicorn itself takes the caller from `X-Forwarded-For` only when the peer is the machine's own loopback address, as a reverse proxy on the same host is. Render fronts every service with Cloudflare and a varying number of its own proxies, so a hop count cannot work there; the app detects Render through its `RENDER` variable and uses `True-Client-IP`.

## Updating data

A scheduled workflow (`.github/workflows/update-data.yml`) runs on the 3rd of each month and can be started by hand from the Actions tab. It regenerates both catalogues from their upstream sources, validates them, runs the format, lint, type and test checks against the new data, and opens a pull request only when the data changed. Its body gives the entry counts and the known exoplanets before and after, every star name within 30 light-years that was added, removed or renamed, since clients may key their own data on those names, and every spectral type and planet count within 30 light-years that changed. On a pull request the workflow opens, GitHub holds the Tests workflow until someone with write access approves the run.

To refresh by hand:

```bash
uv sync --group catalogue
uv run python tools/update_data.py           # everything
uv run python tools/update_data.py stars     # stars only
uv run python tools/update_data.py eclipses  # eclipses only
```

Each upstream fetch is retried, and Gliese falls back to VizieR's CfA mirror when the CDS host fails. The star catalogue is then built by these rules:

- HIPPARCOS distances and positions come from its 2007 reduction, and its V magnitudes and spectral types from the 1997 catalogue. A HIPPARCOS star whose Gaia DR3 match is within 2 magnitudes of its V and has a sound parallax takes Gaia's distance and position instead, and joins that Gaia row and no other. Once the catalogues are merged, every entry beyond 160 light-years is left out, with any Gliese row joined to it or given its distance.
- A Gaia row whose astrometric solution fits poorly (RUWE above 1.4) and whose parallax is under 20 standard errors is left out, since such a parallax is likely spurious. So are eight HIPPARCOS entries that Gaia shows are not nearby stars, and twenty Gliese rows that list a second time a star another entry holds.
- Rows from different catalogues are merged into one entry where their positions, or their positions and distances, agree. A Gliese row is also joined to the Gaia or HIPPARCOS row within 180 arcseconds whose V magnitude is within 0.2 of its own, whatever their distances, since Gliese distances for faint stars are estimates. Within the Gliese catalogue's position errors, rows of like magnitude pair first.
- A component of a Gliese multiple star that no other catalogue lists takes the distance of a component that HIPPARCOS or Gaia measured.
- Each star takes the first of its catalogues' spectral types that its brightness allows. When none fits, a type refused only for its giant luminosity class is cut back to its temperature class (`K5III` to `K5`).
- Gaia gives no spectral types, so a Gaia star's is estimated from its colour and absolute magnitude and marked `(est)`. A red star too faint for a red dwarf is estimated a brown dwarf, `L (est)`, only when its parallax is at least 50 standard errors, and gets no estimate otherwise. A star of BP-RP 1.0 to 2.0 far below the main sequence is estimated a white dwarf, `D (est)`, only with such a parallax too.
- A star's planet count is the number of its own rows in the NASA Exoplanet Archive, matched by Gaia DR3 source, name or HIP number. For a pair that HIPPARCOS or Gaia lists as one star, the count is the pair's. For a star the archive lists, that count replaces the curated table's.
- Positions are propagated to J2000 by the updater itself from each catalogue's own astrometry.

The updaters validate everything before writing:

- Every source must return a minimum number of rows: 3,000 from HIPPARCOS, 1,500 from Gliese, 20,000 from Gaia and 1,000 Exoplanet Archive names.
- Each answer from the Gaia archive, for HIPPARCOS and for Gaia, must hold every row the archive counts as matching, each once.
- Three fast-moving reference stars must sit within 20 arcseconds of their known J2000 positions, and HIPPARCOS must give each its Gaia DR3 match.
- Two entries from different catalogues within 15 arcseconds of each other must agree in distance to within 5 per cent, or half a light-year if that is more: a pair that does not is one star listed twice. Pairs more than 5 magnitudes apart and pairs of named stars are exempt. No name may appear twice.
- A spectral type is refused for a star too faint for its class, a bare M type for a star too bright for a red dwarf, and a giant luminosity class (I to III) for a star too faint to be a giant.
- Curated overrides must land on the right star.
- Eclipse coverage is checked year by year.

A failed or degraded fetch fails the run, so a plausible-looking but wrong catalogue cannot be written. Writes are atomic, and a file is only rewritten when its content changes. `data/manifest.json` records each file's source, entry count and the date it last changed, which `/health` reports.

## Data sources

| Data | Source |
|------|--------|
| Star positions and properties | HIPPARCOS and Gaia DR3 (ESA Gaia archive), and the Gliese Catalogue of Nearby Stars (through VizieR at CDS, or its CfA mirror) |
| Exoplanet counts | NASA Exoplanet Archive |
| Eclipse dates | NASA Five Millennium Catalog of Eclipses (GSFC) |
| Moon and Sun positions | astropy's built-in analytical ephemeris (ERFA). From about 1700 to 2100 its error is far below the rounding of the values returned. Further away the slowing of the Earth's rotation, which is not modelled, shifts midnight UTC, by three hours in year 1, and the Moon's figures with it |
| Voyager distances | JPL Horizons |
| Physical constants | astropy (CODATA and IAU) |

## Project layout

```text
src/first_light/
  app.py          the application: middleware, error handlers, routes
  constants.py    limits and timings of the service
  models.py       request and response schemas
  web/            routes, date formats, client addresses, rate and in-flight limits,
                  body limit, errors, logging
  facts/          the astronomy behind each category, free of the web layer
data/             the catalogues, written by tools/
tools/            the data updaters
tests/            mirrors src/ and tools/
```
