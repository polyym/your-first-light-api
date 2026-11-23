# Changelog

Each release, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/), and versions follow [Semantic Versioning](https://semver.org/), counting from 1.0.0 in this repository.

## [1.1.0] - 2026-11-23

A rebuilt star catalogue, with better distances, fewer stars listed twice and fewer wrong spectral types.

### Changed

- The star catalogue holds 42,426 stars and 957 known exoplanets, against 49,413 and 716. It is rebuilt from current sources by an updater whose rules the 1.0.0 catalogue predated, and each star's planets are counted host by host from the NASA Exoplanet Archive.
- HIPPARCOS distances come from its 2007 reduction, or from Gaia DR3 where Gaia measures the star soundly. 365 HIPPARCOS stars that 1.0.0 listed leave as beyond 160 light-years, 40 of them visible to the naked eye: Gaia DR3 places 312 there, and the 2007 reduction the rest. Gienah (HIP 59803) joins, and Diadem (HIP 64241) moves from 63 to 58 light-years.
- 6,661 Gaia sources that 1.0.0 listed leave, as their astrometric solution fits poorly and their parallax is under 20 standard errors, which makes the parallax likely spurious.
- A component of a Gliese multiple star that only the Gliese catalogue lists takes the distance measured for its system: Gl 853 B is 45.9 light-years away, not 39.6.
- A spectral type that a star's brightness rules out is replaced or cleared; 1.0.0's catalogue held 4,188. Gaia stars are estimated white dwarfs and brown dwarfs, the cool white dwarfs and all brown dwarfs only from a parallax of at least 50 standard errors: 1,903 and 438 estimates, against 1,527 and none, and SIMBAD confirms about two in three of the brown dwarfs. Stars with a type fall from 45,766 (92.6%) to 37,199 (87.7%), mostly with the stars that leave; 3,197 that stay lose a type their brightness or a weaker parallax no longer supports, 3,186 of them an estimate.
- FastAPI goes from 0.162.5 to 0.162.7 and NumPy from 2.5.4 to 2.5.5, and the image builds with uv 0.13.9 rather than 0.13.8. Responses do not change.

### Fixed

- Stars that SIMBAD shows the catalogue lists twice fall from 332 to 13. Capella (HIP 24608), Porrima (HIP 61941), delta Equulei (HIP 104858), 128 Carinae (HIP 45571) and nu Indi (HIP 110618) are each listed once.

## [1.0.0] - 2026-11-20

The first release from this repository.

### Added

- Three POST endpoints, one for each date format, computing 15 categories of facts about a birthday: time alive, the Moon, the light sphere, the stars reached, exoplanets, star classes, planetary ages, body figures, the journey through space, scale comparisons, the universe's age, the Voyager probes, eclipses, the Astronomy Picture of the Day and the Sun's constellation.
- A JSON index at `/` and a health check at `/health`, both answering `HEAD` as well.
- One successful request every 30 seconds per caller, with failed requests giving their slot back. The API's own errors are JSON with a one-line plain-text `detail`, and request bodies are capped at 64 KB.
- Catalogues of 49,413 nearby stars and 913 eclipses, refreshed monthly by a scheduled workflow that opens a pull request for review.
