# Changelog

## 1.1.3

A data-pipeline correctness release. No endpoint, request or response field changes; the values inside the star catalogue change because the pipeline that builds it had several independent faults, and the first automated refresh exposed them.

### Star positions and epochs

- Star positions are now propagated to epoch J2000.0 by the updater itself, from each catalogue's own astrometry (HIPPARCOS at J1991.25, Gaia DR3 at J2016.0, Gliese at B1950.0) with ERFA's rigorous space-motion propagation, instead of being read from VizieR's computed `_RAJ2000`/`_DEJ2000` columns. The September 2026 scheduled refresh showed why that mattered: VizieR had silently stopped applying proper motion to those columns for the Gliese catalogue, so every fast-moving Gliese star (which is to say every nearby one) came back at its 1950 position, tens to hundreds of arcseconds from where HIPPARCOS and Gaia put it. The cross-catalogue match failed for 319 stars, each of which was then listed twice (under its Gliese name at the Gliese distance and under its Gaia designation at the Gaia distance), and 326 more had their Gaia distance replaced by the less reliable Gliese photometric one. Every validator and the full test suite passed on that catalogue. The new propagation reproduces VizieR's HIPPARCOS and Gaia positions to a milliarcsecond and the previous Gliese positions to a fraction of an arcsecond.
- A reference-position guard fails the refresh when any catalogue returns Barnard's Star, Groombridge 1830 or Kapteyn's Star more than 20 arcseconds from their known J2000 positions, so an upstream epoch, unit or column change can never reach the data again.
- A merged entry now takes its position from the same catalogue as its distance (Gaia over HIPPARCOS over Gliese) instead of keeping whichever catalogue came first, so merged stars carry Gaia astrometry rather than a Gliese position quantised to a second of time. The wide distance-checked matching window is now used only when at least one position comes from the coarse Gliese table: two HIPPARCOS or Gaia positions at a common epoch agree to well under an arcsecond for the same star, so two such positions further apart are two stars. Epsilon Indi A had been absorbing the Gaia entry of its brown-dwarf companion 400 arcseconds away while its own Gaia entry survived as a stray duplicate.

### Curated tables

- Eight `HIP_COMMON_NAMES` entries pointed at the wrong star, and because those names also carry hand-curated overrides, the wrongly named stars were overwritten with another star's data: HIP 49908 (Groombridge 1618) was published as Wolf 359, HIP 439 (GJ 1) as Ross 248, HIP 86990 (GJ 693) as Kapteyn's Star while the real Kapteyn's Star stayed listed as `HIP 24186`, HIP 91768 and 91772 (Struve 2398 A/B) as Kruger 60 A/B while the real Kruger 60 stayed listed as `Gl 860` and `HIP 110893`, HIP 94761 (GJ 752 A) as GJ 745 A, and HIP 1476, 84478, 84481 and 92855 as Groombridge 34 B, 36 Ophiuchi A/B and Ross 154. Every mapping was re-verified against SIMBAD by comparing the HIPPARCOS position of the ID with SIMBAD's position for the name. Groombridge 1618, GJ 1, GJ 693 and GJ 752 A return to the catalogue under their own designations; Kapteyn's Star and Kruger 60 A/B are each listed once.
- Fourteen hand-entered coordinates in `KNOWN_STAR_OVERRIDES` and `EXTRA_STARS` were wrong, several by degrees (Luyten's Star, YZ Ceti, Kapteyn's Star, Kruger 60 A/B, Struve 2398 A/B, EZ Aquarii A/B/C, GJ 1061, DX Cancri, LP 890-9, WISE 0855-0714). Besides publishing wrong positions, this defeated the coordinate-based removal of catalogue duplicates, so EZ Aquarii, DX Cancri and GJ 1061 were each listed twice. All curated coordinates are now SIMBAD ICRS J2000.0 values, and a new `OVERRIDE_MISMATCH` validation check fails the run if an override lands on an entry whose catalogue position is more than an arcminute away; the previous override check compared the override with itself after it had been applied and could never fail.
- Gliese rows are now designated by catalogue name plus component (`Gl 559 A`), which is unique across the table. The bare name is not: 403 names cover more than one row, so the old designations collapsed binaries into one entry by chance of ordering and left the other component as a stray duplicate (Groombridge 1830 was listed both as `HIP 57939` and `Gl 451`). The component entries in `GLIESE_COMMON_NAMES` (Alpha Centauri A/B, 61 Cygni A/B, Sirius B, Procyon B and others) had never matched anything because their keys lacked the space. GJ 3323, which hosts two known planets, is listed in the Gliese catalogue under its provisional designation `NN 3323`, so its planets were never matched; the mapping is fixed.
- The Gaia fetch no longer falls back to the EDR3 distances catalogue, which has no parallax column and could never have satisfied the query; a failed Gaia fetch now fails the run through the existing fetch-count guard.

### Catalogue changes

- The shipped catalogue was regenerated with the fixed pipeline: 49,338 stars become 49,413. Within 15 light-years the count goes from 63 to 59: seven phantom entries leave (second copies of Kapteyn's Star, Kruger 60, EZ Aquarii, DX Cancri and GJ 1061, and the stray Gaia entry of Epsilon Indi A), GJ 1 returns as `HIP 439`, Procyon B and the Gliese components Gl 234 B and Gl 473 A/B are listed under their own designations, and Epsilon Indi's brown-dwarf pair appears as its own Gaia entry. `stars_reached`, `naked_eye_stars_reached`, `star_type_breakdown`, `estimated_exoplanets` and every `ra_deg`/`dec_deg` that came from a merged or Gliese-only entry change accordingly. The refresh also picks up the September 2026 NASA Exoplanet Archive counts.

### API hardening

- Request bodies are capped at 64 KB. A valid request is a few hundred bytes, but previously any body was read into memory in full before validation, so a client could post megabytes per request at the cost of a rate-limit slot that was refunded on the resulting 422. Oversized bodies now get a 413 before parsing, whether the size is declared in `Content-Length` or streamed with chunked encoding; the 413 carries CORS headers and refunds the rate-limit slot like every other error.
- `GET /` and `GET /health` also answer `HEAD`, which uptime monitors commonly use and which previously returned 405. `/health` answers 503 when a catalogue failed to load, so platform health checks that look only at the status code take a degraded instance out of rotation.
- Malformed request bodies get plain-English errors: "Request body is not valid JSON." instead of "1: JSON decode error", plus "Request body is required." and "Request body must be a JSON object." for empty and non-object bodies. Field-level errors are unchanged. 413 and 500 are now documented in the OpenAPI schema alongside 422 and 429.
- `age_seconds` is documented as physically elapsed time: astropy subtracts the two dates on the atomic time scale, so the value includes every leap second inserted in the interval and can exceed `age_days` x 86400 by a few seconds (the README example is 741,312,005, not 741,312,000 as it previously claimed). `age_hours` and `age_minutes` derive from it. `age_days` is now plain calendar arithmetic rather than a truncated float, which would have been one day short if a negative leap second were ever inserted.
- Voyager 1 and 2 gain a verified JPL Horizons milestone for 2026-01-01 (169.26 and 141.71 AU); the previous extrapolation from 2025 was already within 0.01 AU, and a test now pins the table to Horizons. The "Time to cross at Voyager 1 speed" comparison reads the probe speed from the constant instead of a duplicated literal.
- The container no longer runs uvicorn's access log: the application's own request log already records every request with the resolved client IP and duration, so each request was being logged twice in different formats.
- The test dependency moves from `httpx` to `httpx2`, which Starlette's test client now expects; the suite no longer emits a deprecation warning on every run.
- CI and the data-refresh workflow use current major versions of `actions/checkout`, `actions/setup-python` and `peter-evans/create-pull-request`, which run on Node 24 and clear the Node 20 deprecation notice GitHub prints on every run.

### Operations

- The scheduled data-refresh workflow additionally requires the repository setting "Allow GitHub Actions to create and approve pull requests"; without it the run pushes the branch and fails at the final step. This is now documented in the workflow and the README.

## 1.1.2

- `CLIENT_IP_HEADER` now defaults to `True-Client-IP` automatically when the app detects it is running on Render (via the platform-set `RENDER` environment variable). Live verification of 1.1.1 showed that services created outside a blueprint never receive the env vars declared in `render.yaml`, so rate limiting kept keying on Render's rotating internal proxy addresses; the safe default removes any dependence on manual dashboard configuration. An explicit `CLIENT_IP_HEADER` still takes precedence.

## 1.1.1

- Fixed client IP extraction on Render, where live testing showed the rate limiter never engaging. Render fronts every service with Cloudflare, so the `X-Forwarded-For` chain contains a variable number of platform hops and the fixed `TRUSTED_PROXY_HOPS=1` selected a proxy address that changed on every request, giving each request a fresh rate-limit bucket. A new `CLIENT_IP_HEADER` setting reads the verified caller address from a platform-set header instead, taking precedence over the hop-count logic; `render.yaml` now sets `CLIENT_IP_HEADER=True-Client-IP`. `TRUSTED_PROXY_HOPS` remains available for deployments behind a conventional proxy chain.

## 1.1.0

A quality and automation release. The client contract is unchanged: no endpoint paths, request fields, response field names or types, or status codes for existing valid cases have been altered. The values inside some existing fields have changed where that is a correctness fix, and a handful of purely additive fields and routes are new.

### Data correctness

- Deduplicated the star catalogue. The old merge logic used a fixed 1 light-year distance tolerance, so the same physical star entered repeatedly under different designations (HIP, Gliese, Gaia DR3) whenever catalogues disagreed about its parallax; famous stars such as Delta Pavonis were listed twice. Matching is now two-tier: cross-catalogue entries at essentially the same position (within 15 arcsec) are treated as one star regardless of distance disagreement, since Gliese photometric parallaxes can be off by tens of percent, while a wider window (absorbing proper-motion drift between catalogue epochs) also requires distance agreement scaled with distance. Entries from the same source catalogue are never merged (protecting real binaries), each entry is absorbed by its closest match, and the merged distance comes from the most reliable source (Gaia over HIPPARCOS over Gliese). Each written entry now records the distance's `source` and the full `sources` list it drew from, so the duplicate check can tell real component pairs (which share a source) from actual duplicates. `stars_reached`, `naked_eye_stars_reached`, `star_type_breakdown` and `estimated_exoplanets` drop accordingly and are now trustworthy.
- Removed `SO 0253+1652` from the hand-curated star list: it is Teegarden's Star's discovery designation and duplicated that star with an incorrect position.
- The catalogue validator now detects positional duplicates (same sky position, disagreeing distance) and fails the run, so this class of corruption can never pass validation again. A test asserts the shipped catalogue is clean.
- Gaia G-band magnitudes are converted to approximate Johnson V (using BP-RP colour, Riello et al. 2021) before being stored, so `naked_eye_visible` no longer compares G-band values against a V-band threshold. Where no conversion is possible the band is recorded and exposed as a new optional `magnitude_band` field on stars.
- Gaia entries without a catalogue MK classification now carry a coarse spectral class estimated from their BP-RP colour (Pecaut and Mamajek 2013 boundaries, with intrinsically faint blue objects classed as white dwarfs). Estimates are marked with an `(est)` suffix so they are always distinguishable from measured types. Previously `star_type_breakdown` reported the vast majority of distant stars as "Unknown".

### Computation fixes (values change, schema does not)

- `photons_emitted` was computed with the Wien-peak photon energy instead of the mean blackbody photon energy and undercounted by about 40 percent; values increase by a factor of about 1.7.
- `full_moons_since_birth` now counts a full moon that falls later in the day on the `as_of` date, consistent with `moon_phase_at_midnight_utc` reporting "Full Moon" for that same date.
- Moon phase names are now centred on the geometric instant of each principal phase, so a moon a few hours before exact full is labelled "Full Moon" rather than "Waxing Gibbous" alongside a 99.9 percent illumination figure.
- `light_arrival_date` and `next_star.arrival_date` are well-formed for every reachable year: years below 1000 are zero-padded (previously `"904-04-01 "`), and arrivals beyond year 9999 use a five-digit year instead of being truncated mid-day.

### Security and robustness

- The rate limiter can no longer be bypassed by varying `X-Forwarded-For`. By default the direct peer address is used and the header is ignored; behind a reverse proxy, set `TRUSTED_PROXY_HOPS` to the number of trusted hops and the limiter uses the entry appended by the first trusted proxy. The Dockerfile no longer tells uvicorn to trust forwarded headers from any peer.
- Requests that fail (4xx or 5xx) no longer consume the caller's 30-second rate-limit slot, so correcting a mistyped date does not cost a wait.
- 429 and 500 responses now carry CORS headers, so browser clients can read the error and the `Retry-After` header instead of an opaque network failure.
- Every 422 body now has `detail` as a plain string, as documented. Previously, request-validation errors (bad `star_limit`, unknown category, missing field) returned FastAPI's list-of-objects shape, contradicting the published schema.
- An explicit empty `categories` list is rejected with a 422 instead of silently returning every category.
- Requests that end in a 500 now appear in the access log with method, path, duration and client IP.
- Data files are written atomically (temporary file plus rename), so an interrupted updater run can never leave a truncated catalogue that breaks the API at import.

### Performance

- `star_limit` now bounds the expensive work: the per-star response models are only built for the slice actually returned, and arrival dates use plain date arithmetic instead of building an astropy `Time` per star (roughly 75 times cheaper). Counts and `next_star` are still computed from the full catalogue. The full test suite runs about three times faster as a side effect.

### Data pipeline automation

- A scheduled GitHub Actions workflow (monthly, also manually triggerable) regenerates both catalogues, validates them, runs the full test suite against the refreshed data, and opens a pull request only when the data actually changed. A separate CI workflow lints and tests every push and pull request.
- `tools/update_data.py` no longer pip-installs anything implicitly; missing dependencies are reported with the exact install command.
- Updaters skip the write entirely when the regenerated content is identical to what is on disk, so refresh runs produce no noise diffs (the eclipse file's `generated` stamp no longer churns).
- Degraded upstream fetches fail the run instead of degrading the data: each star catalogue source and the Exoplanet Archive must return at least half of its expected row count, and eclipse validation checks per-year coverage for lunar as well as solar eclipses, so a single failed century page cannot slip through on totals alone.
- New `data/manifest.json` records the source, entry count, and last-changed date of each data file; `/health` reports the dates as a new `data_updated` field.

### Additive API changes

- New `sun_constellation` category: the IAU constellation the Sun was actually in on the birthday (one of 13, including Ophiuchus) alongside the traditional tropical star sign, and whether the two agree; roughly 2,000 years of axial precession means they usually do not.
- New `next_solar_eclipse` and `next_lunar_eclipse` fields in the eclipses category: the first eclipse of each kind strictly after `as_of`, omitted beyond the catalogue's 2100 horizon.
- New `next_full_moon_date` field in the moon category, from the same synodic model as the full-moon count.
- New `stars_reached_this_year` field in the stars category: catalogue stars the birth light reached in the 365.25 days up to `as_of`.
- New `GET /` route returning a small JSON index (name, version, docs, endpoints), so the deployed base URL is no longer a bare 404.
- New optional `magnitude_band` field on star entries.
- New optional `data_updated` field on `/health`.
- The `categories` list now accepts up to 15 entries to cover the new category.

### Documentation and packaging

- Corrected the ephemeris claim: astropy's built-in analytical ephemeris (ERFA) is used, not JPL DE440s. The Dockerfile step that claimed to warm a DE440s cache (and downloaded nothing) is removed.
- `pydantic` and `pyerfa` are declared as direct dependencies, and the Docker image installs from a fully pinned `requirements.lock` for reproducible builds. The redundant `requirements.txt` is removed; local setup uses the editable install.
- Data files are written with LF line endings on every platform (and pinned via `.gitattributes`), so a catalogue regenerated on Windows and one regenerated by the Linux CI runner are byte-identical and never diff on line endings.
- `as_of` is documented as defaulting to the current UTC date, and the handler now derives it explicitly from UTC.
- The response-model documentation now states that fields with no value within a requested category (for example `birthday_star` with no match) are omitted, matching actual behaviour.
- Corrected the `universe_expansion_percent` description: the value is the percentage growth of the cosmological scale factor, not fractional growth of the observable universe.
- `render.yaml` pins `PORT` and sets `TRUSTED_PROXY_HOPS=1`; the Dockerfile honours a platform-provided `PORT` and execs uvicorn as PID 1 so SIGTERM produces a graceful shutdown.
- The `mypy` strict configuration is now actually enforced: `src/` passes `mypy --strict` (with the pydantic plugin) and CI runs it on every push and pull request.

## 1.0.0

Initial release.
