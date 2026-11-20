"""How far the two Voyager probes have flown in a lifetime."""

from datetime import date
from itertools import pairwise

from first_light.facts.age import Lifetime
from first_light.facts.physics import AU_KM
from first_light.models import FirstLightResponse, VoyagerStatus

VOYAGER_1_LAUNCH = date(1977, 9, 5)
VOYAGER_2_LAUNCH = date(1977, 8, 20)

# Speeds relative to the Sun, in round figures. Both probes slow a
# little every year: JPL Horizons gives 17.0 and 15.4 km/s for 2015,
# and 16.9 and 15.3 for late 2026.
VOYAGER_1_SPEED_KM_S = 17.0
VOYAGER_2_SPEED_KM_S = 15.4

# (date, distance from the Sun's centre in AU at 00:00) from JPL Horizons
# (ssd.jpl.nasa.gov/horizons): the launch, each encounter, each crossing
# into interstellar space and every 1 January. A distance between two
# milestones is interpolated, which is out by 0.21 AU at most, in the
# first year of flight, and after the last one extrapolated.
VOYAGER_1_MILESTONES = (
    (date(1977, 9, 5), 1.01),  # Launch
    (date(1978, 1, 1), 1.92),
    (date(1979, 1, 1), 4.88),
    (date(1979, 3, 5), 5.28),  # Jupiter
    (date(1980, 1, 1), 6.90),
    (date(1980, 11, 12), 9.51),  # Saturn
    (date(1981, 1, 1), 9.74),
    (date(1982, 1, 1), 12.06),
    (date(1983, 1, 1), 15.07),
    (date(1984, 1, 1), 18.39),
    (date(1985, 1, 1), 21.88),
    (date(1986, 1, 1), 25.44),
    (date(1987, 1, 1), 29.03),
    (date(1988, 1, 1), 32.65),
    (date(1989, 1, 1), 36.29),
    (date(1990, 1, 1), 39.92),
    (date(1991, 1, 1), 43.56),
    (date(1992, 1, 1), 47.19),
    (date(1993, 1, 1), 50.83),
    (date(1994, 1, 1), 54.46),
    (date(1995, 1, 1), 58.09),
    (date(1996, 1, 1), 61.71),
    (date(1997, 1, 1), 65.33),
    (date(1998, 1, 1), 68.94),
    (date(1999, 1, 1), 72.55),
    (date(2000, 1, 1), 76.16),
    (date(2001, 1, 1), 79.77),
    (date(2002, 1, 1), 83.38),
    (date(2003, 1, 1), 86.98),
    (date(2004, 1, 1), 90.57),
    (date(2005, 1, 1), 94.18),
    (date(2006, 1, 1), 97.77),
    (date(2007, 1, 1), 101.36),
    (date(2008, 1, 1), 104.95),
    (date(2009, 1, 1), 108.54),
    (date(2010, 1, 1), 112.12),
    (date(2011, 1, 1), 115.70),
    (date(2012, 1, 1), 119.28),
    (date(2012, 8, 25), 121.60),  # Entered interstellar space
    (date(2013, 1, 1), 122.87),
    (date(2014, 1, 1), 126.44),
    (date(2015, 1, 1), 130.02),
    (date(2016, 1, 1), 133.59),
    (date(2017, 1, 1), 137.17),
    (date(2018, 1, 1), 140.74),
    (date(2019, 1, 1), 144.31),
    (date(2020, 1, 1), 147.88),
    (date(2021, 1, 1), 151.45),
    (date(2022, 1, 1), 155.01),
    (date(2023, 1, 1), 158.57),
    (date(2024, 1, 1), 162.13),
    (date(2025, 1, 1), 165.70),
    (date(2026, 1, 1), 169.26),
)
VOYAGER_2_MILESTONES = (
    (date(1977, 8, 20), 1.01),  # Launch
    (date(1978, 1, 1), 1.91),
    (date(1979, 1, 1), 4.49),
    (date(1979, 7, 9), 5.32),  # Jupiter
    (date(1980, 1, 1), 6.05),
    (date(1981, 1, 1), 8.09),
    (date(1981, 8, 26), 9.60),  # Saturn
    (date(1982, 1, 1), 9.73),
    (date(1983, 1, 1), 10.99),
    (date(1984, 1, 1), 13.19),
    (date(1985, 1, 1), 15.93),
    (date(1986, 1, 1), 18.92),
    (date(1986, 1, 24), 19.12),  # Uranus
    (date(1987, 1, 1), 21.72),
    (date(1988, 1, 1), 24.77),
    (date(1989, 1, 1), 28.04),
    (date(1989, 8, 25), 30.21),  # Neptune
    (date(1990, 1, 1), 31.07),
    (date(1991, 1, 1), 33.60),
    (date(1992, 1, 1), 36.26),
    (date(1993, 1, 1), 39.02),
    (date(1994, 1, 1), 41.86),
    (date(1995, 1, 1), 44.75),
    (date(1996, 1, 1), 47.69),
    (date(1997, 1, 1), 50.68),
    (date(1998, 1, 1), 53.69),
    (date(1999, 1, 1), 56.73),
    (date(2000, 1, 1), 59.79),
    (date(2001, 1, 1), 62.87),
    (date(2002, 1, 1), 65.96),
    (date(2003, 1, 1), 69.06),
    (date(2004, 1, 1), 72.18),
    (date(2005, 1, 1), 75.31),
    (date(2006, 1, 1), 78.45),
    (date(2007, 1, 1), 81.58),
    (date(2008, 1, 1), 84.73),
    (date(2009, 1, 1), 87.88),
    (date(2010, 1, 1), 91.03),
    (date(2011, 1, 1), 94.19),
    (date(2012, 1, 1), 97.34),
    (date(2013, 1, 1), 100.51),
    (date(2014, 1, 1), 103.67),
    (date(2015, 1, 1), 106.83),
    (date(2016, 1, 1), 110.00),
    (date(2017, 1, 1), 113.17),
    (date(2018, 1, 1), 116.34),
    (date(2018, 11, 5), 119.02),  # Entered interstellar space
    (date(2019, 1, 1), 119.51),
    (date(2020, 1, 1), 122.68),
    (date(2021, 1, 1), 125.86),
    (date(2022, 1, 1), 129.03),
    (date(2023, 1, 1), 132.20),
    (date(2024, 1, 1), 135.37),
    (date(2025, 1, 1), 138.54),
    (date(2026, 1, 1), 141.71),
)

PROBES = (
    ("Voyager 1", VOYAGER_1_LAUNCH, VOYAGER_1_SPEED_KM_S, VOYAGER_1_MILESTONES),
    ("Voyager 2", VOYAGER_2_LAUNCH, VOYAGER_2_SPEED_KM_S, VOYAGER_2_MILESTONES),
)


def add_voyagers(result: FirstLightResponse, life: Lifetime) -> None:
    """Fills the voyagers category."""
    result.voyagers = [
        _probe_status(name, launch, speed, milestones, life)
        for name, launch, speed, milestones in PROBES
    ]


def distance_au(day: date, milestones: tuple[tuple[date, float], ...]) -> float:
    """Gives a probe's distance from the Sun on ``day``.

    Before launch it is the launch distance. After the last milestone
    the last two milestones' rate carries on.
    """
    if day <= milestones[0][0]:
        return milestones[0][1]
    if day >= milestones[-1][0]:
        (start, start_au), (end, end_au) = milestones[-2:]
        rate = (end_au - start_au) / (end - start).days
        return end_au + (day - end).days * rate
    return next(
        start_au + (day - start).days / (end - start).days * (end_au - start_au)
        for (start, start_au), (end, end_au) in pairwise(milestones)
        if start <= day <= end
    )


def _probe_status(
    name: str,
    launch: date,
    speed_km_s: float,
    milestones: tuple[tuple[date, float], ...],
    life: Lifetime,
) -> VoyagerStatus:
    """Works out how far one probe has flown since the birthday."""
    # Counted from launch for a probe launched after the birthday.
    flown_au = distance_au(life.as_of, milestones) - distance_au(
        max(life.birth, launch), milestones
    )
    return VoyagerStatus(
        name=name,
        launch_date=launch.isoformat(),
        distance_travelled_since_birth_km=round(flown_au * AU_KM, 2),
        distance_travelled_since_birth_au=round(flown_au, 2),
        speed_km_s=speed_km_s,
        was_launched_before_birth=launch < life.birth,
    )
