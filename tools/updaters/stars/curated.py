"""Hand-verified tables: names, corrections and extra stars.

Every position here is a SIMBAD ICRS position at epoch J2000.0.
"""

from typing import Any

# Common names of HIPPARCOS stars, by HIP number. Each mapping is
# confirmed by comparing the HIPPARCOS position of the number with
# SIMBAD's position for the name, because numbers are easy to confuse
# (HIP 49908 is Groombridge 1618, not Wolf 359; HIP 91768 and 91772 are
# Struve 2398 A and B, not Kruger 60 A and B). A wrong mapping renames a
# real star and, when the name also has an override, overwrites that
# star's data with another's, so the real star vanishes and the named
# one is counted twice. The OVERRIDE_MISMATCH check fails the run in
# that second case.
HIP_COMMON_NAMES: dict[int, str] = {
    70890: "Proxima Centauri",
    71683: "Alpha Centauri A",
    71681: "Alpha Centauri B",
    87937: "Barnard's Star",
    32349: "Sirius A",
    # Sirius B is not resolved in HIPPARCOS; see EXTRA_STARS.
    16537: "Epsilon Eridani",
    8102: "Tau Ceti",
    37279: "Procyon A",
    36208: "Luyten's Star",
    54035: "Lalande 21185",
    88601: "70 Ophiuchi A",
    104214: "61 Cygni A",
    104217: "61 Cygni B",
    57548: "Ross 128",
    114046: "Lacaille 9352",
    92403: "Ross 154",
    # Ross 248 and Wolf 359 are too faint for HIPPARCOS; they come from
    # the Gliese catalogue (Gl 905 and Gl 406).
    97649: "Altair",
    91262: "Vega",
    113368: "Fomalhaut",
    49908: "Groombridge 1618",
    80824: "Wolf 1061",
    108870: "Epsilon Indi A",
    96100: "Sigma Draconis",
    99240: "Delta Pavonis",
    15510: "82 Eridani",
    37826: "Pollux",
    69673: "Arcturus",
    3829: "Van Maanen's Star",
    1475: "Groombridge 34 A",
    # Groombridge 34 B has no HIPPARCOS entry; see EXTRA_STARS.
    110893: "Kruger 60 A",
    91768: "Struve 2398 A",
    91772: "Struve 2398 B",
    105090: "Lacaille 8760",
    24186: "Kapteyn's Star",
    84405: "36 Ophiuchi A",
    84478: "36 Ophiuchi C",
    5643: "YZ Ceti",
    93873: "GJ 745 A",
    93899: "GJ 745 B",
    106440: "GJ 832",
}

# HIPPARCOS entries that are not nearby stars, each checked against
# Gaia DR3. No other catalogue here lists any of them. HIP 114110 and
# HIP 114176 are the scattered light of a bright star half an arcminute
# away: Gaia has no source there. The rest are stars Gaia puts far
# beyond the catalogue: HIP 10529, 68 light-years away by its 2007
# HIPPARCOS parallax, is 778 by Gaia's, which Gaia DR3's own match of
# HIPPARCOS stars does not link to it. Four would leave anyway, HIP
# 21000 through its Gaia match and HIP 85605, 98681 and 114176 through
# 2007 parallaxes under five standard errors, and stay listed in case
# either source changes.
SPURIOUS_HIP_IDS = frozenset(
    {10529, 21000, 82724, 82725, 85605, 98681, 114110, 114176}
)

# Gliese rows that list a second time a star another entry already
# holds, each confirmed with SIMBAD. Beside each is the star and, where
# the catalogue lists it, the entry that holds it. Their positions are
# too coarse for the merge to join them, so
# each would stay as a copy of the star, most at the wrong distance. A
# component beside a HIPPARCOS entry is too close for HIPPARCOS to
# resolve, and that entry's V already holds its light: Capella's HIP
# 24608, at V 0.08, is Gl 194 A and B together.
DUPLICATE_GLIESE_IDS = frozenset(
    {
        "Gl 194 B",  # Capella: HIP 24608
        "Gl 337 B",  # pi01 Cnc: HIP 45170
        "Gl 340 B",  # HD 79969: HIP 45617
        "Gl 340.1 B",  # 128 Car: HIP 45571
        "Gl 366.1 B",  # theta Ant: Gl 366.1 A
        "Gl 482 B",  # Porrima: HIP 61941
        "Gl 534.1 B",  # HD 121384 B: Gaia DR3 6064816017535011072
        "Gl 644 B",  # HD 152751: HIP 82817
        "Gl 750 B",  # HD 179930: HIP 94739
        "Gl 822 B",  # delta Equ: HIP 104858
        "Gl 828 B",  # L 353-9
        "Gl 855.1 B",  # nu Ind: HIP 110618
        "NN 3063",  # Smethells 177: HIP 4189
        "NN 3101",  # G 274-72
        "NN 3203",  # AE For: HIP 14568
        "NN 3231 B",  # HD 21663 B: NN 3232
        "NN 3419",  # L 814-1
        "NN 3444",  # LP 88-196
        "NN 4285",  # L 119-44: Gaia DR3 6392188629658709888
        "Wo 9490 B",  # BD+20 3010: HIP 71914
    }
)

# Common names of Gliese catalogue rows, keyed by the designation
# gliese.gliese_name builds (such as "Gl 559 A") and confirmed the same
# way as HIP_COMMON_NAMES. A name that also appears in HIP_COMMON_NAMES,
# KNOWN_STAR_OVERRIDES or EXTRA_STARS makes the Gliese row merge with,
# or give way to, that entry rather than stay as a second copy of the
# star under its Gliese designation.
GLIESE_COMMON_NAMES: dict[str, str] = {
    "Gl 551": "Proxima Centauri",
    "Gl 559 A": "Alpha Centauri A",
    "Gl 559 B": "Alpha Centauri B",
    "Gl 699": "Barnard's Star",
    "Gl 406": "Wolf 359",
    "Gl 411": "Lalande 21185",
    "Gl 244 A": "Sirius A",
    "Gl 244 B": "Sirius B",
    "Gl 65 A": "Luyten 726-8A (BL Ceti)",
    "Gl 65 B": "Luyten 726-8B (UV Ceti)",
    "Gl 729": "Ross 154",
    "Gl 905": "Ross 248",
    "Gl 144": "Epsilon Eridani",
    "Gl 887": "Lacaille 9352",
    "Gl 447": "Ross 128",
    "Gl 866 AB": "EZ Aquarii A",  # an unresolved triple in the catalogue
    "Gl 280 A": "Procyon A",
    "Gl 280 B": "Procyon B",
    "Gl 820 A": "61 Cygni A",
    "Gl 820 B": "61 Cygni B",
    "Gl 725 A": "Struve 2398 A",
    "Gl 725 B": "Struve 2398 B",
    "Gl 15 A": "Groombridge 34 A",
    "Gl 15 B": "Groombridge 34 B",
    "Gl 845": "Epsilon Indi A",
    "GJ 1111": "DX Cancri",
    "Gl 71": "Tau Ceti",
    "Gl 54.1": "YZ Ceti",
    "Gl 273": "Luyten's Star",
    "Gl 191": "Kapteyn's Star",
    "Gl 825": "Lacaille 8760",
    "Gl 860 A": "Kruger 60 A",
    "Gl 860 B": "Kruger 60 B",
    "Gl 83.1": "TZ Arietis",
    "Gl 35": "Van Maanen's Star",
    "Gl 628": "Wolf 1061",
    "Gl 380": "Groombridge 1618",
    "Gl 702 A": "70 Ophiuchi A",
    "Gl 702 B": "70 Ophiuchi B",
    "Gl 663 A": "36 Ophiuchi A",
    "Gl 663 B": "36 Ophiuchi B",
    "Gl 764": "Sigma Draconis",
    "Gl 780": "Delta Pavonis",
    "Gl 139": "82 Eridani",
    "Gl 768": "Altair",
    "Gl 721": "Vega",
    "Gl 881": "Fomalhaut",
    "Gl 286": "Pollux",
    "Gl 541": "Arcturus",
    "Gl 687": "GJ 687",
    "Gl 674": "GJ 674",
    "Gl 876": "GJ 876",
    "Gl 832": "GJ 832",
    "Gl 581": "GJ 581",
    "Gl 667 C": "GJ 667 C",
    "Gl 251": "GJ 251",
    "Gl 436": "GJ 436",
    "Gl 745 A": "GJ 745 A",
    "Gl 745 B": "GJ 745 B",
    "GJ 1061": "GJ 1061",
    "GJ 1002": "GJ 1002",
    "GJ 1214": "GJ 1214",
    "NN 3323": "GJ 3323",  # CNS3 provisional number; GJ 3323 has 2 planets
}

# The fields of each row in _OVERRIDE_ROWS and _EXTRA_ROWS, after the
# name: distance in light-years, spectral type, V magnitude, known
# exoplanets, RA and Dec in degrees.
_FIELDS = (
    "distance_ly",
    "spectral_type",
    "apparent_magnitude",
    "known_exoplanets",
    "ra_deg",
    "dec_deg",
)

# The most important nearby stars, from SIMBAD and the NASA Exoplanet
# Archive (planet counts of November 2026). Applied after every merge
# step, so they win over any catalogue value. Only the planet count
# gives way: the archive's replaces it for a star the archive lists,
# since those counts change. The validator checks that each lands on
# an entry the catalogues put at the same position, so an override
# can never silently overwrite a different star.
_OVERRIDE_ROWS = (
    ("Proxima Centauri", 4.2465, "M5.5Ve", 11.13, 2, 217.4289, -62.6795),
    ("Alpha Centauri A", 4.365, "G2V", -0.01, 0, 219.9021, -60.834),
    ("Alpha Centauri B", 4.365, "K1V", 1.35, 0, 219.8961, -60.8375),
    ("Barnard's Star", 5.9577, "M4.0V", 9.51, 4, 269.4521, 4.6934),
    ("Wolf 359", 7.8558, "M6.5Ve", 13.54, 0, 164.1205, 7.0147),
    ("Lalande 21185", 8.3044, "M2.0V", 7.52, 2, 165.8341, 35.9699),
    ("Sirius A", 8.6094, "A1V", -1.46, 0, 101.2872, -16.7161),
    ("Ross 154", 9.6813, "M3.5Ve", 10.44, 0, 282.4557, -23.8362),
    ("Ross 248", 10.2903, "M5.5V", 12.29, 0, 355.4793, 44.1774),
    ("Epsilon Eridani", 10.475, "K2V", 3.73, 1, 53.2327, -9.4583),
    ("Lacaille 9352", 10.721, "M0.5V", 7.34, 4, 346.4668, -35.8531),
    ("Ross 128", 11.007, "M4.0V", 11.13, 1, 176.935, 0.8046),
    ("61 Cygni A", 11.403, "K5V", 5.21, 0, 316.7247, 38.7494),
    ("61 Cygni B", 11.403, "K7V", 6.03, 0, 316.7303, 38.742),
    ("Procyon A", 11.402, "F5IV-V", 0.37, 0, 114.8255, 5.225),
    ("Groombridge 34 A", 11.624, "M1.5V", 8.08, 2, 4.5954, 44.023),
    ("Tau Ceti", 11.912, "G8.5V", 3.5, 3, 26.017, -15.9375),
    ("Epsilon Indi A", 11.869, "K5V", 4.69, 1, 330.8402, -56.786),
    ("Luyten's Star", 12.366, "M3.5V", 9.87, 2, 111.8521, 5.2258),
    ("YZ Ceti", 12.132, "M4.5V", 12.07, 3, 18.1277, -16.999),
    ("Kapteyn's Star", 12.777, "sdM1", 8.85, 1, 77.9191, -45.0184),
    ("Kruger 60 A", 13.149, "M3V", 9.79, 0, 336.9982, 57.695),
    ("Kruger 60 B", 13.149, "M4V", 11.41, 0, 336.9991, 57.6972),
    ("70 Ophiuchi A", 16.592, "K0V", 4.03, 0, 271.3635, 2.5001),
    ("Sigma Draconis", 18.798, "G9V", 4.67, 0, 293.09, 69.6612),
    ("Delta Pavonis", 19.893, "G8IV", 3.56, 0, 302.1817, -66.1821),
    ("Altair", 16.73, "A7V", 0.76, 0, 297.6958, 8.8683),
    ("Vega", 25.04, "A0V", 0.03, 0, 279.2347, 38.7837),
    ("Fomalhaut", 25.13, "A3V", 1.16, 0, 344.4127, -29.6222),
    ("Pollux", 33.72, "K0IIIb", 1.14, 1, 116.329, 28.0262),
    ("Arcturus", 36.66, "K1.5III", -0.05, 0, 213.9153, 19.1824),
)

# Stars the catalogue queries miss or do not resolve, and sub-stellar
# objects, with planet counts of November 2026, which give way to the
# archive's as an override's do. Each replaces any catalogue entry of
# the same name, and merge.dedup_by_coordinates removes catalogue
# entries at its position, so a wrong coordinate here leaves the star
# listed twice: once curated and once under its Gaia or Gliese
# designation.
_EXTRA_ROWS = (
    # Brown dwarfs and other sub-stellar objects.
    ("Luhman 16A", 6.5, "L7.5", 23.25, 0, 162.329, -53.3196),
    ("Luhman 16B", 6.5, "T0.5", 24.07, 0, 162.3292, -53.3199),
    ("WISE 0855-0714", 7.43, "Y4", 25.0, 0, 133.8189, -7.247),
    ("WISE 1506+7027", 16.817, "T6", 22.0, 0, 226.7185, 70.457),
    ("WISE 0350-5658", 18.49, "Y1", 24.0, 0, 57.5025, -56.9734),
    ("UGPS 0722-0540", 13.43, "T9", 23.8, 0, 110.6163, -5.676),
    ("LP 944-20", 20.961, "M9.0V", 18.5, 0, 54.8969, -35.4288),
    ("WISE 1541-2250", 19.54, "Y0.5", 24.5, 0, 235.4679, -22.8402),
    ("2MASS J0415-0935", 18.65, "T8", 22.0, 0, 63.8314, -9.5852),
    # Stars missing from, or unresolved in, the catalogue queries.
    ("Luyten 726-8A (BL Ceti)", 8.728, "M5.5Ve", 12.54, 0, 24.7557, -17.9507),
    ("Luyten 726-8B (UV Ceti)", 8.728, "M6.0Ve", 12.95, 0, 24.7568, -17.9503),
    ("Sirius B", 8.6094, "DA2", 8.44, 0, 101.2888, -16.7169),
    ("EZ Aquarii A", 11.266, "M5.0V", 13.33, 0, 339.6399, -15.2999),
    ("EZ Aquarii B", 11.266, "M5.5V", 13.27, 0, 339.6399, -15.2999),
    ("EZ Aquarii C", 11.266, "M6.5V", 14.03, 0, 339.6399, -15.2999),
    ("Struve 2398 A", 11.525, "M3.0V", 8.94, 1, 280.6946, 59.6304),
    ("Struve 2398 B", 11.525, "M3.5V", 9.7, 1, 280.6954, 59.6269),
    ("Groombridge 34 B", 11.624, "M3.5V", 11.06, 0, 4.6076, 44.0272),
    ("GJ 1061", 11.991, "M5.5V", 13.09, 3, 53.9987, -44.5127),
    ("DX Cancri", 11.826, "M6.5Ve", 14.78, 0, 127.4556, 26.776),
    # "SO 0253+1652" is this star's discovery designation, not a second
    # star, so it must not get an entry of its own.
    ("Teegarden's Star", 12.497, "M7.0V", 15.4, 3, 43.2537, 16.8813),
    ("SCR 1845-6357 A", 13.064, "M8.5V", 17.39, 0, 281.2719, -63.9632),
    ("DENIS J1048-3956", 13.17, "M8.5V", 17.39, 0, 162.0607, -39.9352),
    ("SCR J1546-5534", 27.386, "M7.5V", 17.3, 0, 236.6737, -55.5799),
    ("GJ 876", 15.238, "M4.0V", 10.17, 4, 343.3197, -14.2637),
    ("GJ 832", 16.085, "M1.5V", 8.66, 1, 323.3916, -49.009),
    ("TRAPPIST-1", 40.66, "M8V", 18.8, 7, 346.6224, -5.0414),
    ("LP 890-9", 104.9, "M6V", 18.12, 2, 64.1298, -28.3147),
)


def _fields(values: list[Any]) -> dict[str, Any]:
    return dict(zip(_FIELDS, values, strict=True))


KNOWN_STAR_OVERRIDES: dict[str, dict[str, Any]] = {
    name: _fields(values) for name, *values in _OVERRIDE_ROWS
}
EXTRA_STARS: list[dict[str, Any]] = [
    {"name": name, **_fields(values)} for name, *values in _EXTRA_ROWS
]

# Host names the NASA Exoplanet Archive uses for stars that this
# catalogue names differently.
EXOPLANET_NAME_ALIASES: dict[str, list[str]] = {
    "Proxima Centauri": ["Proxima Cen", "GJ 551", "Gl 551"],
    "Alpha Centauri B": ["alf Cen B", "GJ 559 B"],
    "Barnard's Star": ["Barnard's star", "GJ 699", "Gl 699"],
    "Lalande 21185": ["GJ 411", "Gl 411"],
    "Epsilon Eridani": ["eps Eri", "GJ 144", "Gl 144"],
    "Tau Ceti": ["tau Cet", "GJ 71", "Gl 71"],
    "Lacaille 9352": ["GJ 887", "Gl 887"],
    "Epsilon Indi A": ["eps Ind A", "GJ 845", "Gl 845"],
    "Luyten's Star": ["GJ 273", "Gl 273"],
    "YZ Ceti": ["YZ Cet", "GJ 54.1"],
    "Kapteyn's Star": ["Kapteyn's star", "GJ 191"],
    "Wolf 1061": ["GJ 628"],
    "Ross 128": ["GJ 447"],
    "Teegarden's Star": ["Teegarden's Star"],
    "Wolf 359": ["CN Leo", "GJ 406"],
    "Ross 154": ["GJ 729"],
    "Ross 248": ["GJ 905"],
    "Sirius A": ["Sirius", "GJ 244 A"],
    "GJ 876": ["GJ 876", "Gl 876"],
    "GJ 832": ["GJ 832", "Gl 832"],
    "GJ 1061": ["GJ 1061"],
    "GJ 667 C": ["GJ 667 C"],
    "GJ 581": ["GJ 581", "Gl 581"],
    "Pollux": ["Pollux"],
    "70 Ophiuchi A": ["70 Oph", "GJ 702"],
    "Struve 2398 A": ["Gl 725 A", "GJ 725 A"],
    "Struve 2398 B": ["Gl 725 B", "GJ 725 B"],
    # The archive gives this host no HIP, HD or Gaia DR3 designation.
    "HIP 85850": ["TOI-5997"],
}

# Fast-moving stars every fetch must return close to these positions,
# keyed by source and then by that catalogue's own identifier. A fetch
# whose coordinates are at the wrong epoch, in other units or from
# another column puts them tens to hundreds of arcseconds away.
REFERENCE_POSITIONS: dict[str, dict[str, tuple[float, float]]] = {
    "hipparcos": {
        "87937": (269.45208, 4.69336),  # Barnard's Star
        "57939": (178.24487, 37.71868),  # Groombridge 1830
        "24186": (77.91912, -45.01843),  # Kapteyn's Star
    },
    "gliese": {
        "Gl 699": (269.45208, 4.69336),
        "Gl 451 A": (178.24487, 37.71868),
        "Gl 191": (77.91912, -45.01843),
    },
    "gaia": {
        "4472832130942575872": (269.45208, 4.69336),
        "4034171629042489088": (178.24487, 37.71868),
        "4810594479418041856": (77.91912, -45.01843),
    },
}

# Gaia DR3's match of each HIPPARCOS reference star, which the
# HIPPARCOS fetch must carry: without its Gaia matches, that fetch
# would keep some 350 stars from beyond the edge, and every other check
# would pass.
REFERENCE_GAIA_MATCHES: dict[str, str] = {
    "87937": "4472832130942575872",  # Barnard's Star
    "57939": "4034171629042489088",  # Groombridge 1830
    "24186": "4810594479418041856",  # Kapteyn's Star
}
