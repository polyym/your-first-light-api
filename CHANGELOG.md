# Changelog

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
