"""The star catalogue updater, which rebuilds data/stars.json.

It queries HIPPARCOS and Gaia DR3 from the ESA Gaia archive, the
Gliese Catalogue of Nearby Stars through VizieR and planet counts from
the NASA Exoplanet Archive, retrying each, moves every position to epoch
J2000.0, merges the catalogues into one entry per star, corrects that
from hand-verified tables, validates it and writes it. The write is
atomic and happens only when the content changed; a failed fetch or
check exits non-zero and leaves the file as it was.

Run it from the repository root, normally through the single entry
point that also maintains data/manifest.json:

    python tools/update_data.py stars

or on its own as ``python -m tools.updaters.stars``.

Modules, in pipeline order: ``hipparcos``, ``gliese`` (through
``vizier``) and ``gaia`` fetch, ``astrometry`` moves positions to J2000.0,
``merge`` combines entries (``entry``) with the ``curated`` tables,
``photometry`` converts magnitudes and cleans spectral types,
``exoplanets`` adds planet counts, ``validate`` checks, ``write``
writes, and ``main`` runs the steps in order.
"""
