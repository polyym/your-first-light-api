"""Magnitudes and spectral types: Gaia conversions and clean-up."""

import math
import re
from typing import NamedTuple

from tools.updaters.stars.astrometry import LY_PER_PARSEC
from tools.updaters.stars.entry import Star, sources_of

# Stands in for a magnitude the catalogue does not give; entries still
# carrying it are dropped before writing.
MISSING_MAGNITUDE = 99.0

# The BP-RP range over which the G to V relation holds.
G_TO_V_MIN_BP_RP = -0.5
G_TO_V_MAX_BP_RP = 5.0

# Absolute magnitudes are apparent magnitudes at this distance.
ABSOLUTE_MAGNITUDE_DISTANCE_PC = 10
# Fainter than this, Gaia's BP-RP colours are too uncertain to give a
# class: most such rows within the catalogue's reach have a colour and
# absolute magnitude that fit no star.
MAX_COLOUR_G_MAG = 19.0
# Bluer than this and fainter than WHITE_DWARF_MIN_ABS_G_MAG in
# absolute G is far below the main sequence: a white dwarf. The white
# dwarf sequence in Gaia's HR diagram ends at WHITE_DWARF_MAX_ABS_G_MAG.
WHITE_DWARF_MAX_BP_RP = 1.0
WHITE_DWARF_MIN_ABS_G_MAG = 10.0
WHITE_DWARF_MAX_ABS_G_MAG = 16.0
# The reddest BP-RP colour of each main-sequence class, bluest first
# (Pecaut and Mamajek 2013).
_CLASS_MAX_BP_RP = (
    ("B", 0.0),
    ("A", 0.37),
    ("F", 0.77),
    ("G", 0.98),
    ("K", 1.84),
    ("M", 5.0),
)
_RED_DWARF_MIN_BP_RP = dict(_CLASS_MAX_BP_RP)["K"]
# The faintest red dwarf in Pecaut and Mamajek's table (version
# 2022.04.16), M9.5V. Their brown dwarfs run on from 16.60 (L0V) to
# 18.50 (L5V); T dwarfs, fainter still, are rarely seen by Gaia, whose
# colours cannot tell the two apart, so an estimate calls both L.
FAINTEST_RED_DWARF_ABS_G_MAG = 16.40
# Red rows that faint with a parallax under this many standard errors
# move across the sky at a median 2.6 km/s, as distant stars with
# spurious parallaxes would, against 23 km/s for the rest.
MIN_BROWN_DWARF_PARALLAX_SNR = 20

# The absolute V magnitudes of each class's dwarfs, from the brightest
# (earliest subtype) to the faintest (latest), from Pecaut and Mamajek
# (2013), table version 2022.04.16.
DWARF_ABS_V_MAG = {
    "O": (-5.80, -4.05),
    "B": (-3.90, 0.60),
    "A": (0.99, 2.43),
    "F": (2.57, 4.35),
    "G": (4.48, 5.55),
    "K": (5.78, 8.56),
    "M": (8.80, 19.75),
}
# How far beyond its class's dwarf magnitudes a star may lie and still
# fit its type: unresolved binaries are up to 0.75 mag brighter, young
# stars brighter still, metal-poor ones fainter, and a parallax of five
# standard errors leaves 0.4 mag of error in the absolute magnitude.
SPECTRAL_TYPE_MARGIN_MAG = 2.0
# The faintest absolute V magnitude of a giant (luminosity class III),
# at the foot of the red giant branch; bright giants and supergiants are
# brighter still.
GIANT_FAINTEST_ABS_V_MAG = 2.0

# Catalogue spectral types that stand for "no type". The class letters
# of the HIPPARCOS "O...", "WN..." and "R..." belong to luminous stars,
# none of them within the catalogue's reach.
_PLACEHOLDER_TYPES = ("R...", "O...", "WN...", "...")
# A giant luminosity class (I, II or III) anywhere in a type.
_GIANT_CLASS = re.compile(r"I{1,3}(?!V)")
# A giant luminosity class where the API reads one to label the star a
# giant. It repeats first_light.facts.stars.GIANT_TYPE, and a test
# keeps the two equal: the updater runs without the app on its path,
# and importing that module would load the data/stars.json it rebuilds.
GIANT_LUMINOSITY_TYPE = re.compile(
    r"[A-Z][0-9.]*(?:[/-][A-Z]?[0-9.]*)?(?:m[A-Z][0-9.]*)?\s*I{1,3}(?!V)"
)


class SpectralTypeFixes(NamedTuple):
    """What ``fix_spectral_types`` changed, in entries."""

    # Types rewritten by normalise_spectral_type alone.
    normalised: int
    # Types that did not fit, replaced by another catalogue's.
    replaced: int
    # Giant types that did not fit, cut back to their temperature class.
    trimmed: int
    # Types that did not fit, with nothing to replace them.
    cleared: int


def gaia_g_to_v(gmag: float, bp_rp: float | None) -> float | None:
    """Approximates Johnson V from Gaia DR3 G and BP-RP colour.

    Uses the Gaia DR3 photometric relation (Riello et al. 2021),
    ``G - V = -0.02704 + 0.01424x - 0.2156x^2 + 0.01426x^3`` with
    ``x = BP-RP``. G can be up to about 1.5 mag brighter than V for red
    stars, so a raw G in the V-band field inflates naked-eye counts.

    Returns:
        The estimated V magnitude, or ``None`` when the colour is
        missing or outside the relation's range.
    """
    if bp_rp is None or not (G_TO_V_MIN_BP_RP < bp_rp < G_TO_V_MAX_BP_RP):
        return None
    g_minus_v = (
        -0.02704 + 0.01424 * bp_rp - 0.2156 * bp_rp**2 + 0.01426 * bp_rp**3
    )
    return gmag - g_minus_v


def absolute_magnitude(magnitude: float, dist_ly: float) -> float:
    """The magnitude a star would have at 10 parsecs."""
    dist_pc = dist_ly / LY_PER_PARSEC
    return magnitude - 5 * math.log10(dist_pc / ABSOLUTE_MAGNITUDE_DISTANCE_PC)


def estimate_spectral_class(
    bp_rp: float | None,
    gmag: float,
    dist_ly: float,
    parallax_snr: float | None = None,
) -> str:
    """Estimates a coarse spectral class from Gaia colour.

    Takes the BP-RP colour (``None`` when Gaia has none), the G
    magnitude, the distance and the parallax in standard errors
    (``None`` when unknown). The result carries an ``(est)`` marker so
    estimates stay apart from catalogue MK types. The API classifies a
    type by its first letter, so estimates still group with their class
    in ``star_type_breakdown``.

    A red star more than ``SPECTRAL_TYPE_MARGIN_MAG`` fainter in
    absolute G than the faintest red dwarf is a brown dwarf, ``"L
    (est)"``, when its parallax is at least
    ``MIN_BROWN_DWARF_PARALLAX_SNR`` standard errors. That rests on the
    magnitude, not the colour, so it holds at any G. Any other estimate
    takes the star for a dwarf or a white dwarf, so there is none for a
    star fainter than ``MAX_COLOUR_G_MAG``, one fainter than the white
    dwarf sequence, or one whose absolute V magnitude is more than
    ``SPECTRAL_TYPE_MARGIN_MAG`` outside the ``DWARF_ABS_V_MAG`` range
    of the class its colour gives.

    Returns:
        A class such as ``"M (est)"``, or ``""`` when there is no
        estimate.
    """
    if bp_rp is None or gmag == MISSING_MAGNITUDE or dist_ly <= 0:
        return ""
    abs_g = absolute_magnitude(gmag, dist_ly)
    if (
        parallax_snr is not None
        and parallax_snr >= MIN_BROWN_DWARF_PARALLAX_SNR
        and bp_rp >= _RED_DWARF_MIN_BP_RP
        and abs_g > FAINTEST_RED_DWARF_ABS_G_MAG + SPECTRAL_TYPE_MARGIN_MAG
    ):
        return "L (est)"
    if gmag > MAX_COLOUR_G_MAG:
        return ""
    if bp_rp < WHITE_DWARF_MAX_BP_RP and abs_g > WHITE_DWARF_MIN_ABS_G_MAG:
        return "D (est)" if abs_g <= WHITE_DWARF_MAX_ABS_G_MAG else ""
    letter = next(
        (letter for letter, max_bp_rp in _CLASS_MAX_BP_RP if bp_rp < max_bp_rp),
        None,
    )
    if letter is None:
        return ""
    # Judged on the magnitude the entry publishes, as the validator is.
    vmag = gaia_g_to_v(gmag, bp_rp)
    abs_mag = absolute_magnitude(gmag if vmag is None else vmag, dist_ly)
    brightest, faintest = DWARF_ABS_V_MAG[letter]
    if not (
        brightest - SPECTRAL_TYPE_MARGIN_MAG
        <= abs_mag
        <= faintest + SPECTRAL_TYPE_MARGIN_MAG
    ):
        return ""
    return f"{letter} (est)"


def contradicts_magnitude(spectral_type: str, abs_v: float) -> bool:
    """Whether a star of this absolute V magnitude cannot have the type.

    The class is the type's first letter, as the API reads it. No star
    more than ``SPECTRAL_TYPE_MARGIN_MAG`` fainter than the faintest
    dwarf of its class has the type, since the class's giants are
    brighter still. For class M, neither does a star that much brighter
    than the brightest M dwarf, unless the type names a giant luminosity
    class (I to III), as HIPPARCOS and Gliese do for every M giant: a
    bare M type is a dwarf's, and Capella is far too bright for its
    "M1: comp". Stars of the other classes that bright may be
    subgiants and giants whose type omits the luminosity class. And no
    star more than ``SPECTRAL_TYPE_MARGIN_MAG`` fainter than any giant
    has a type naming a giant luminosity class: the HIPPARCOS "K1III(p)"
    of AB Doradus, a K dwarf, would make the API call it a giant.

    A type whose first letter is not a class in ``DWARF_ABS_V_MAG`` is
    never contradicted: subdwarfs ("sd..."), white dwarfs ("D...")
    and brown dwarfs ("L...", "T...").
    """
    limits = DWARF_ABS_V_MAG.get(spectral_type[:1])
    if limits is None:
        return False
    brightest, faintest = limits
    if abs_v > faintest + SPECTRAL_TYPE_MARGIN_MAG:
        return True
    if (
        GIANT_LUMINOSITY_TYPE.match(spectral_type)
        and abs_v > GIANT_FAINTEST_ABS_V_MAG + SPECTRAL_TYPE_MARGIN_MAG
    ):
        return True
    return (
        spectral_type[0] == "M"
        and not _GIANT_CLASS.search(spectral_type)
        and abs_v < brightest - SPECTRAL_TYPE_MARGIN_MAG
    )


def temperature_class(spectral_type: str) -> str:
    """The part of a giant's type before its luminosity class.

    ``"K5III"`` gives ``"K5"`` and ``"G0/G1III"`` gives ``"G0/G1"``.
    A type that names no giant luminosity class where the API reads
    one gives ``""``.
    """
    match = GIANT_LUMINOSITY_TYPE.match(spectral_type)
    return match.group().rstrip("I").rstrip() if match else ""


def normalise_spectral_type(sp: str) -> str:
    """Rewrites a catalogue spectral type in the form the API reads.

    Collapses repeated spaces, drops the archaic dwarf prefix ("dM5.5e"
    to "M5.5e") and the trailing "J" binary flag, clears placeholders
    such as "R...", and upper-cases class letters ("k-m" to "K-M",
    "m+" to "M+"). A leading "s" or "d" stays lower-case, since it
    starts a luminosity prefix such as the "sd" of "sdM1".
    """
    while "  " in sp:
        sp = sp.replace("  ", " ")
    if len(sp) >= 2 and sp[0] == "d" and sp[1] in "MKGFAB":
        sp = sp[1:]
    sp = sp.rstrip()
    if sp.endswith("J"):
        sp = sp[:-1].rstrip()
    if sp in _PLACEHOLDER_TYPES:
        sp = ""
    if len(sp) == 3 and sp[1] == "-" and sp[0].isalpha() and sp[2].isalpha():
        sp = sp.upper()
    if sp and sp[0].islower() and sp[0] not in "sd":
        sp = sp[0].upper() + sp[1:]
    return sp


def fix_spectral_types(stars: list[Star]) -> SpectralTypeFixes:
    """Gives each entry the first of its catalogues' types that fits it.

    A merged entry holds a type from each catalogue it drew on, in merge
    order (``_spectral_types``): HIPPARCOS, Gliese, then the Gaia
    estimate. Each is normalised (``normalise_spectral_type``) and the
    entry takes the first that is not empty and that its absolute
    magnitude does not contradict (``contradicts_magnitude``). When
    none fits, it takes the temperature class of the first type whose
    giant luminosity class is all that is wrong with it
    (``temperature_class``): the HIPPARCOS "K5III" of a star as faint
    as a K dwarf is a K5 with the wrong luminosity class, not a star
    of no known type. Otherwise it has no type. A curated entry's type
    is only normalised: it is hand-verified, so a contradiction there
    is for the validator to report. The same goes for an entry whose
    distance is not positive, which has no absolute magnitude. Works
    in place, on entries that all have a magnitude.
    """
    normalised = replaced = trimmed = cleared = 0
    for s in stars:
        types = s.get("_spectral_types", [s["spectral_type"]])
        candidates = [normalise_spectral_type(sp) for sp in types]
        first = next((sp for sp in types if sp), "")
        # The type the entry would have with no magnitude check, so a
        # placeholder giving way counts as normalised, not replaced.
        usual = next((sp for sp in candidates if sp), "")
        chosen = usual
        was_trimmed = False
        # The validator reports a distance that gives no absolute
        # magnitude.
        if sources_of(s) and s["distance_ly"] > 0:
            abs_v = absolute_magnitude(
                s["apparent_magnitude"], s["distance_ly"]
            )
            chosen = next(
                (
                    sp
                    for sp in candidates
                    if sp and not contradicts_magnitude(sp, abs_v)
                ),
                "",
            )
            if not chosen:
                chosen = next(
                    (
                        sp
                        for sp in map(temperature_class, candidates)
                        if sp and not contradicts_magnitude(sp, abs_v)
                    ),
                    "",
                )
                was_trimmed = bool(chosen)
        if was_trimmed:
            trimmed += 1
        elif chosen != usual:
            if chosen:
                replaced += 1
            else:
                cleared += 1
        elif usual != first:
            normalised += 1
        s["spectral_type"] = chosen
    return SpectralTypeFixes(normalised, replaced, trimmed, cleared)


def remove_unknown_magnitudes(stars: list[Star]) -> int:
    """Drops entries with no magnitude in place.

    Returns:
        The number of entries dropped.
    """
    before = len(stars)
    stars[:] = [
        s for s in stars if s["apparent_magnitude"] != MISSING_MAGNITUDE
    ]
    return before - len(stars)
