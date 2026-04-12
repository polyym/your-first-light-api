"""Physical and astronomical constants for the computation engine.

No FastAPI or Pydantic imports — pure astronomical data, orbital
parameters, biological averages, and Voyager probe milestones.
All values are documented with their sources.
"""

from datetime import date

from astropy import constants as const
from astropy import units as u

# ---------------------------------------------------------------------------
# Fundamental
# ---------------------------------------------------------------------------
# Speed of light in km/s (derived from astropy).
LIGHT_SPEED_KM_S = const.c.to(u.km / u.s).value

# Stefan-Boltzmann constant in W / (m^2 * K^4).
STEFAN_BOLTZMANN = const.sigma_sb.to(
    u.W / u.m**2 / u.K**4
).value

SECONDS_PER_YEAR = 365.25 * 24 * 3600  # Julian year
SIDEREAL_DAY_SECONDS = 86164.0905  # 23h 56m 4.0905s
AU_KM = 149_597_870.7  # 1 AU in km (IAU 2012)
MPC_KM = (1 * u.Mpc).to(u.km).value  # 1 Megaparsec in km
LY_KM = (1 * u.lyr).to(u.km).value  # 1 light-year in km
HOURS_PER_YEAR = 365.25 * 24  # 8766 hours per Julian year

# ---------------------------------------------------------------------------
# Galactic / cosmological
# ---------------------------------------------------------------------------
MILKY_WAY_DIAMETER_LY = 87_400  # D25 isophotal diameter (26.8 kpc)
EARTH_ORBITAL_SPEED_KM_S = 29.78  # Mean orbital speed around the Sun
SUN_GALACTIC_ORBITAL_SPEED_KM_S = 230  # Sun's speed around galactic centre
GALACTIC_ORBITAL_PERIOD_MYR = 225  # Galactic year in millions of years
HUBBLE_CONSTANT = 70  # km/s/Mpc (rounded consensus estimate)
UNIVERSE_AGE_YEARS = 13.787e9  # Age of the universe (Planck 2018)
OBSERVABLE_UNIVERSE_DIAMETER_LY = 93.016e9  # Comoving diameter
GREAT_ATTRACTOR_SPEED_KM_S = 600  # Milky Way speed toward Great Attractor

# ---------------------------------------------------------------------------
# Solar system distances
# ---------------------------------------------------------------------------
MOON_DISTANCE_KM = 384_400
SUN_DISTANCE_KM = AU_KM  # 1 AU
PLUTO_DISTANCE_KM = 5_906_376_272  # semi-major axis
EARTH_VOLUME_KM3 = 1.08321e12

# ---------------------------------------------------------------------------
# Voyager probes — piecewise distance milestones (JPL Horizons)
# Each entry: (date, heliocentric_distance_au)
# Source: NASA JPL Horizons System (ssd.jpl.nasa.gov/horizons/)
# ---------------------------------------------------------------------------
VOYAGER_1_LAUNCH = date(1977, 9, 5)
VOYAGER_2_LAUNCH = date(1977, 8, 20)

# Current approximate heliocentric speed (post-cruise phase)
VOYAGER_1_SPEED_KM_S = 17.0
VOYAGER_2_SPEED_KM_S = 15.4

VOYAGER_1_MILESTONES: tuple[tuple[date, float], ...] = (
    (date(1977, 9, 5), 1.01),       # Launch
    (date(1979, 3, 5), 5.28),       # Jupiter closest approach
    (date(1980, 11, 12), 9.50),     # Saturn closest approach
    (date(1985, 1, 1), 21.88),      # Cruise
    (date(1990, 1, 1), 39.92),
    (date(1995, 1, 1), 58.08),
    (date(2000, 1, 1), 76.16),
    (date(2005, 1, 1), 94.18),
    (date(2010, 1, 1), 112.12),
    (date(2012, 8, 25), 121.60),    # Entered interstellar space
    (date(2015, 1, 1), 130.02),
    (date(2020, 1, 1), 147.87),
    (date(2025, 1, 1), 165.70),
)

VOYAGER_2_MILESTONES: tuple[tuple[date, float], ...] = (
    (date(1977, 8, 20), 1.02),      # Launch
    (date(1979, 7, 9), 5.31),       # Jupiter closest approach
    (date(1981, 8, 25), 9.58),      # Saturn closest approach
    (date(1986, 1, 24), 19.11),     # Uranus closest approach
    (date(1989, 8, 25), 30.21),     # Neptune closest approach
    (date(1995, 1, 1), 44.74),
    (date(2000, 1, 1), 59.79),
    (date(2005, 1, 1), 75.31),
    (date(2010, 1, 1), 91.03),
    (date(2015, 1, 1), 106.83),
    (date(2018, 11, 5), 119.01),    # Entered interstellar space
    (date(2020, 1, 1), 122.68),
    (date(2025, 1, 1), 138.55),
)

# ---------------------------------------------------------------------------
# Planetary orbital periods (Earth days)
# ---------------------------------------------------------------------------
PLANET_YEAR_DAYS = {
    "Mercury": 87.97, "Venus": 224.7, "Earth": 365.25,
    "Mars": 687.0, "Jupiter": 4_332.59, "Saturn": 10_755.70,
    "Uranus": 30_688.5, "Neptune": 60_195.0, "Pluto": 90_560.0,
}

# ---------------------------------------------------------------------------
# Biological
# ---------------------------------------------------------------------------
BODY_TEMP_K = 310.15  # Average human body temperature (37 C)
AMBIENT_TEMP_K = 293.15  # Assumed ambient room temperature (20 C)
BODY_SURFACE_AREA_M2 = 1.7  # Average adult body surface area
AVG_HEARTBEATS_PER_MIN = 72  # Resting heart rate
AVG_BREATHS_PER_MIN = 15  # Average adult respiratory rate
AVG_BLINKS_PER_MIN = 17  # Spontaneous blink rate (waking hours only)
AVG_IR_PHOTON_ENERGY_J = 1.99e-20  # ~10 um IR peak at 310 K (hc/lambda)
WAKING_FRACTION = 2 / 3  # ~16 h waking out of 24 h

# ---------------------------------------------------------------------------
# Lunar
# ---------------------------------------------------------------------------
SYNODIC_MONTH = 29.530588853  # days

# Known New Moon reference: 2000-01-06 18:14 UTC (Julian Day 2451550.26)
NEW_MOON_JD = 2451550.26

MOON_PHASES = [
    (0, "New Moon"),
    (1, "Waxing Crescent"),
    (7.38, "First Quarter"),
    (8, "Waxing Gibbous"),
    (14.77, "Full Moon"),
    (15.5, "Waning Gibbous"),
    (22.15, "Third Quarter"),
    (22.75, "Waning Crescent"),
]

# ---------------------------------------------------------------------------
# Derived / domain-specific thresholds
# ---------------------------------------------------------------------------
HABITABLE_FRACTION = 0.07  # ~7% of known exoplanets per Kepler stats
BIRTHDAY_STAR_TOLERANCE_LY = 2.0  # max distance mismatch for birthday star
NAKED_EYE_MAG_LIMIT = 6.5  # apparent magnitude threshold
