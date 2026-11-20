"""Physical and astronomical constants, whichever category uses them.

Figures about one category's own subject live beside it: the planets'
years in ``age``, a body's in ``body``, the probes' in ``voyagers``.
"""

from astropy import constants as const
from astropy import units as u

LIGHT_SPEED_KM_S = const.c.to(u.km / u.s).value
STEFAN_BOLTZMANN_W_M2_K4 = const.sigma_sb.to(u.W / u.m**2 / u.K**4).value
BOLTZMANN_J_K = const.k_B.value

DAYS_PER_JULIAN_YEAR = 365.25
SECONDS_PER_YEAR = DAYS_PER_JULIAN_YEAR * 24 * 3600
HOURS_PER_YEAR = DAYS_PER_JULIAN_YEAR * 24
SIDEREAL_DAY_SECONDS = 86164.0905  # 23 h 56 min 4.0905 s

AU_KM = 149_597_870.7  # IAU 2012
LY_KM = (1 * u.lyr).to(u.km).value
MPC_KM = (1 * u.Mpc).to(u.km).value

MOON_DISTANCE_KM = 384_400
SUN_DISTANCE_KM = AU_KM
PLUTO_DISTANCE_KM = 5_906_376_272  # Semi-major axis
EARTH_VOLUME_KM3 = 1.08321e12
EARTH_ORBITAL_SPEED_KM_S = 29.78  # Mean speed around the Sun

MILKY_WAY_DIAMETER_LY = 87_400  # D25 isophotal diameter, 26.8 kpc
SUN_GALACTIC_ORBITAL_SPEED_KM_S = 230
GALACTIC_ORBITAL_PERIOD_MYR = 225
GREAT_ATTRACTOR_SPEED_KM_S = 600  # The Milky Way's speed towards it
HUBBLE_CONSTANT_KM_S_MPC = 70  # Rounded consensus value
UNIVERSE_AGE_YEARS = 13.787e9  # Planck 2018
OBSERVABLE_UNIVERSE_DIAMETER_LY = 93.016e9  # Comoving

SYNODIC_MONTH_DAYS = 29.530588853
