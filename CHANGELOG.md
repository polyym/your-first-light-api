# Changelog

Each release, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/), and versions follow [Semantic Versioning](https://semver.org/), counting from 1.0.0 in this repository.

## [1.0.0] - 2026-11-20

The first release from this repository.

### Added

- Three POST endpoints, one for each date format, computing 15 categories of facts about a birthday: time alive, the Moon, the light sphere, the stars reached, exoplanets, star classes, planetary ages, body figures, the journey through space, scale comparisons, the universe's age, the Voyager probes, eclipses, the Astronomy Picture of the Day and the Sun's constellation.
- A JSON index at `/` and a health check at `/health`, both answering `HEAD` as well.
- One successful request every 30 seconds per caller, with failed requests giving their slot back. The API's own errors are JSON with a one-line plain-text `detail`, and request bodies are capped at 64 KB.
- Catalogues of 49,413 nearby stars and 913 eclipses, refreshed monthly by a scheduled workflow that opens a pull request for review.
