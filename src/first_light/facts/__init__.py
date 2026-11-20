"""The astronomy behind each response category, free of the web layer."""

import warnings

from astropy.utils import iers
from erfa import ErfaWarning

# The API makes no outbound requests. Left on, astropy downloads a newer
# leap-second table on the first request of a process once the bundled
# one nears expiry. The bundled tables come from astropy-iers-data, which
# Dependabot keeps current.
iers.conf.auto_download = False

# ERFA calls years outside its leap-second table "dubious": birthdays
# before 1960 and dates a few years ahead. Both are expected here. From
# about 1700 to 2100 the difference is far below the rounding of every
# value returned; further away it grows, to three hours in year 1.
warnings.filterwarnings("ignore", category=ErfaWarning)
