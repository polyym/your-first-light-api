"""Request and response schemas: the API's public contract.

Class docstrings and field descriptions become the OpenAPI schema
served at /docs, so they are written for the API's callers. The order
of the fields is the order of the keys in a response. Each request
schema carries the body that /docs offers to send: a birthday alone,
since a schema with no example is filled field by field, which gives
as_of the text "string".
"""

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from first_light.constants import (
    DATE_TEXT_MAX_LENGTH,
    STAR_LIMIT_DEFAULT,
    STAR_LIMIT_MAX,
)

Category = Literal[
    "time_alive",
    "moon",
    "light_sphere",
    "stars",
    "exoplanets",
    "star_classification",
    "planetary_ages",
    "body_stats",
    "cosmic_journey",
    "scale_comparisons",
    "universe_perspective",
    "voyagers",
    "eclipses",
    "links",
    "sun_constellation",
]

ALL_CATEGORIES: set[str] = set(get_args(Category))


class ErrorResponse(BaseModel):
    """The body of every error response."""

    detail: str = Field(
        ...,
        description="What went wrong, as one plain sentence.",
        examples=["Birthday must be in the past."],
    )


class RateLimitResponse(BaseModel):
    """The body of a 429. The Retry-After header gives whole seconds."""

    detail: str = Field(
        ...,
        description=(
            "The wait in seconds, rounded up to a tenth, is the first "
            "number in the sentence."
        ),
        examples=[
            "Rate limited. Please wait 25.3 seconds before trying again.",
        ],
    )


class HealthResponse(BaseModel):
    """Whether the catalogues are loaded, and when they last changed."""

    status: Literal["ok", "degraded"] = Field(
        ..., description="degraded, with a 503, when a catalogue is empty."
    )
    stars_loaded: int = Field(..., description="Stars in the catalogue.")
    eclipses_loaded: int = Field(
        ..., description="Solar eclipses in the catalogue."
    )
    data_updated: dict[str, str] | None = Field(
        None,
        description=(
            "Each data file and the date (YYYY-MM-DD) it last changed. "
            "Left out when the data has no manifest."
        ),
    )


class _BaseRequest(BaseModel):
    """The fields every date format shares."""

    categories: list[Category] | None = Field(
        None,
        description=(
            "Categories to include. Leave it out for all of them; an empty "
            "list is rejected."
        ),
        min_length=1,
        max_length=len(ALL_CATEGORIES),
    )
    star_limit: int = Field(
        STAR_LIMIT_DEFAULT,
        description=(
            "The most stars to list, nearest first. Counts and next_star "
            "always cover the whole catalogue, and stars_remaining says "
            "how many were left out."
        ),
        ge=1,
        le=STAR_LIMIT_MAX,
    )


# The example birthday is an arbitrary date, the same in all three
# formats. Its day is above 12, so no format can be read as another.
class BigEndianRequest(_BaseRequest):
    """A birthday written as YYYY-MM-DD."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"birthday": "1998-11-15"}]}
    )

    birthday: str = Field(
        ...,
        description="Date of birth, YYYY-MM-DD.",
        examples=["1998-11-15"],
        max_length=DATE_TEXT_MAX_LENGTH,
    )
    as_of: str | None = Field(
        None,
        description=(
            "The date to measure up to, YYYY-MM-DD. Leave it out for "
            "today's UTC date."
        ),
        max_length=DATE_TEXT_MAX_LENGTH,
    )


class MiddleEndianRequest(_BaseRequest):
    """A birthday written as MM/DD/YYYY."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"birthday": "11/15/1998"}]}
    )

    birthday: str = Field(
        ...,
        description="Date of birth, MM/DD/YYYY.",
        examples=["11/15/1998"],
        max_length=DATE_TEXT_MAX_LENGTH,
    )
    as_of: str | None = Field(
        None,
        description=(
            "The date to measure up to, MM/DD/YYYY. Leave it out for "
            "today's UTC date."
        ),
        max_length=DATE_TEXT_MAX_LENGTH,
    )


class LittleEndianRequest(_BaseRequest):
    """A birthday written as DD/MM/YYYY."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"birthday": "15/11/1998"}]}
    )

    birthday: str = Field(
        ...,
        description="Date of birth, DD/MM/YYYY.",
        examples=["15/11/1998"],
        max_length=DATE_TEXT_MAX_LENGTH,
    )
    as_of: str | None = Field(
        None,
        description=(
            "The date to measure up to, DD/MM/YYYY. Leave it out for "
            "today's UTC date."
        ),
        max_length=DATE_TEXT_MAX_LENGTH,
    )


class StarInfo(BaseModel):
    """A star the light from the birthday has reached."""

    name: str = Field(..., description="Common or catalogue name.")
    distance_ly: float = Field(..., description="Distance from the Sun.")
    spectral_type: str = Field(
        ...,
        description=(
            "MK spectral type, empty when unknown. '(est)' marks a class "
            "estimated from colour."
        ),
    )
    spectral_class: str = Field(
        ...,
        description=(
            "Readable class, with its letter in brackets, such as "
            "'Red dwarf (M)'. Subdwarfs are 'Subdwarf (S)'."
        ),
    )
    apparent_magnitude: float = Field(
        ..., description="Brightness seen from Earth; lower is brighter."
    )
    magnitude_band: str | None = Field(
        None,
        description=(
            "Photometric band of apparent_magnitude: 'V' (visual) or 'G' "
            "(Gaia broad-band, where no V estimate exists). Left out when "
            "unknown."
        ),
    )
    known_exoplanets: int = Field(
        ..., description="Confirmed exoplanets orbiting the star."
    )
    your_age_at_light_arrival_years: float = Field(
        ...,
        description=(
            "Age when the light reached the star, equal to its distance "
            "in light-years."
        ),
    )
    light_arrival_date: str = Field(
        ...,
        description=(
            "The date (YYYY-MM-DD) the light reached the star. Always on "
            "or before as_of."
        ),
    )
    naked_eye_visible: bool = Field(
        ...,
        description="Bright enough to see without a telescope (mag 6.5).",
    )
    ra_deg: float | None = Field(
        None, description="Right ascension, J2000, in degrees."
    )
    dec_deg: float | None = Field(
        None, description="Declination, J2000, in degrees."
    )


class NextStar(BaseModel):
    """The nearest star the light has not reached yet."""

    name: str
    distance_ly: float = Field(..., description="Distance from the Sun.")
    arrives_in_years: float = Field(
        ..., description="Years from as_of until the light arrives."
    )
    arrival_date: str = Field(
        ...,
        description=(
            "YYYY-MM-DD, with a five-digit year for an arrival after 9999."
        ),
    )


class LightSphere(BaseModel):
    """The sphere of light that left Earth on the birthday."""

    radius_ly: float = Field(..., description="Equal to the age in years.")
    diameter_ly: float
    radius_km: float
    radius_au: float
    volume_cubic_ly: float
    surface_area_sq_ly: float
    milky_way_diameter_percent: float = Field(
        ..., description="Diameter as a percentage of the Milky Way's."
    )
    observable_universe_diameter_percent: float = Field(
        ...,
        description=(
            "Diameter as a percentage of the observable universe's "
            "(93 billion light-years)."
        ),
    )


class PlanetaryAge(BaseModel):
    """Age counted in another planet's years."""

    planet: str
    age: float = Field(..., description="Age in that planet's years.")
    orbital_period_earth_days: float = Field(
        ..., description="One year on that planet, in Earth days."
    )


class BodyStats(BaseModel):
    """Rough lifetime figures for an average adult body."""

    estimated_heartbeats: int
    estimated_breaths: int
    estimated_blinks: int = Field(
        ..., description="Blinks during waking hours."
    )
    photons_emitted: float = Field(
        ...,
        description=(
            "Infrared photons radiated, treating the body as a blackbody "
            "at 310 K."
        ),
    )
    thermal_power_watts: float = Field(
        ...,
        description=(
            "Net heat radiated: blackbody emission at 310 K less what is "
            "absorbed from a 293 K (20 °C) room. About 180 W."
        ),
    )


class CosmicJourney(BaseModel):
    """How far the Earth, the Sun and the galaxy have carried someone."""

    earth_distance_around_sun_km: float
    earth_orbits_completed: float = Field(
        ..., description="Julian years elapsed, with the fraction."
    )
    galactic_distance_km: float = Field(
        ..., description="How far the Sun has moved round the galaxy."
    )
    galactic_orbit_degrees: float = Field(
        ..., description="The share of one galactic orbit, in degrees."
    )
    great_attractor_distance_km: float = Field(
        ...,
        description="How far the Milky Way has moved towards the Great "
        "Attractor.",
    )
    universe_expansion_percent: float = Field(
        ...,
        description=(
            "Growth of the cosmological scale factor, to first order "
            "(H0 times the time elapsed)."
        ),
    )


class ScaleComparison(BaseModel):
    """The light sphere set against a familiar measure."""

    label: str
    value: float
    unit: str = Field(..., description="Such as 'trips' or 'years'.")


class MoonPhaseAtBirth(BaseModel):
    """The Moon at midnight UTC on the birthday."""

    phase_name: str = Field(
        ..., description="Such as 'Waxing Crescent' or 'Full Moon'."
    )
    illumination_percent: float = Field(
        ..., description="The share of the disc lit, 0 to 100."
    )
    moon_age_days: float = Field(
        ...,
        description=(
            "Its place in the cycle in mean days: 0 at new moon and 14.77 "
            "at full, from its angle to the Sun. Days since the actual "
            "new moon can differ by up to about a day."
        ),
    )


class BirthdayStar(BaseModel):
    """The star whose distance in light-years best matches the age.

    The light seen from it today left it around the day of the birth,
    and the birth's own light is reaching it about now. It may not be
    among the stars reached yet.
    """

    name: str
    distance_ly: float
    spectral_type: str
    difference_ly: float = Field(
        ..., description="How far the distance is from the age; 0 is exact."
    )


class SunConstellation(BaseModel):
    """Where the Sun really was on the birthday, against the star sign."""

    constellation: str = Field(
        ...,
        description=(
            "The IAU constellation holding the Sun at midnight UTC: one "
            "of the 13 on its path, Ophiuchus included. Thousands of "
            "years ahead, precession also brings Cetus and Orion."
        ),
    )
    zodiac_sign: str = Field(
        ..., description="The traditional (tropical) star sign for the date."
    )
    matches_zodiac_sign: bool = Field(
        ...,
        description=(
            "Usually false: some 2,000 years of precession have moved the "
            "Sun's path by about one constellation since the signs were "
            "fixed."
        ),
    )


class VoyagerStatus(BaseModel):
    """How far a Voyager probe has flown since the birthday."""

    name: str = Field(..., description="'Voyager 1' or 'Voyager 2'.")
    launch_date: str = Field(..., description="YYYY-MM-DD.")
    distance_travelled_since_birth_km: float = Field(
        ...,
        description=(
            "Its gain in distance from the Sun, counted from launch for a "
            "birthday before it."
        ),
    )
    distance_travelled_since_birth_au: float
    speed_km_s: float = Field(
        ..., description="Its approximate speed relative to the Sun."
    )
    was_launched_before_birth: bool


class EclipseCounts(BaseModel):
    """Eclipses in a lifetime, from NASA's catalogue for 1900 to 2100."""

    solar_eclipses: int = Field(
        ...,
        description=(
            "Solar eclipses from the birthday to as_of, both days included."
        ),
    )
    lunar_eclipses: int = Field(
        ...,
        description=(
            "Lunar eclipses from the birthday to as_of, both days included."
        ),
    )
    total_eclipses: int = Field(
        ...,
        description=(
            "solar_eclipses plus lunar_eclipses, not only eclipses of totality."
        ),
    )
    next_solar_eclipse: str | None = Field(
        None,
        description=(
            "The first solar eclipse after as_of (YYYY-MM-DD). Left out "
            "when the catalogue cannot tell it: for an as_of before 31 "
            "December 1899, or after its last eclipse in 2100."
        ),
    )
    next_lunar_eclipse: str | None = Field(
        None,
        description=(
            "The first lunar eclipse after as_of (YYYY-MM-DD). Left out "
            "when the catalogue cannot tell it: for an as_of before 31 "
            "December 1899, or after its last eclipse in 2100."
        ),
    )
    coverage_note: str | None = Field(
        None,
        description=(
            "Present when the lifetime reaches outside 1900 to 2100, to "
            "say which part the counts cover."
        ),
    )


class FirstLightResponse(BaseModel):
    """Facts about a birthday, for the categories asked for.

    birthday and as_of are always present. Every other field belongs to
    one category and appears only when that category is asked for, and
    then only when it has a value: birthday_star without a close match,
    next_star once every star is reached and stars_remaining when the
    list is complete are left out.
    """

    birthday: str = Field(..., description="YYYY-MM-DD.")
    as_of: str = Field(..., description="YYYY-MM-DD.")

    age_years: float | None = Field(
        None, description="time_alive: elapsed Julian years (365.25 days)."
    )
    age_days: int | None = Field(
        None, description="time_alive: whole calendar days."
    )
    age_hours: int | None = Field(
        None, description="time_alive: whole hours, from age_seconds."
    )
    age_minutes: int | None = Field(
        None, description="time_alive: whole minutes, from age_seconds."
    )
    age_seconds: int | None = Field(
        None,
        description=(
            "time_alive: whole SI seconds from midnight UTC to midnight "
            "UTC. Physical time, so it differs from age_days x 86400 by "
            "the leap seconds in between: up to 37 more, or one fewer "
            "for a short span across UTC's backward steps of 1961 and "
            "1968."
        ),
    )
    earth_rotations: float | None = Field(
        None,
        description=(
            "time_alive: sidereal days, turns of the Earth relative to the "
            "equinox, about one more than the days for each year."
        ),
    )
    leap_years_lived_through: int | None = Field(
        None, description="time_alive: 29 Februaries from birth to as_of."
    )

    moon_phase_at_midnight_utc: MoonPhaseAtBirth | None = Field(
        None, description="moon."
    )
    full_moons_since_birth: int | None = Field(
        None,
        description=(
            "moon: full moons from midnight UTC on the birthday to the "
            "end of the as_of day."
        ),
    )
    next_full_moon_date: str | None = Field(
        None,
        description=(
            "moon: the UTC date of the first full moon at or after "
            "midnight on as_of (YYYY-MM-DD, five digits after 9999)."
        ),
    )

    light_sphere: LightSphere | None = Field(None, description="light_sphere.")
    speed_of_light_km_s: float | None = Field(None, description="light_sphere.")

    stars_reached: int | None = Field(
        None, description="stars: catalogue stars the light has reached."
    )
    naked_eye_stars_reached: int | None = Field(
        None, description="stars: those bright enough to see unaided."
    )
    stars_reached_this_year: int | None = Field(
        None,
        description="stars: those reached in the 365.25 days to as_of.",
    )
    stars_remaining: str | None = Field(
        None,
        description=(
            "stars: when the list stops at star_limit, how many more were "
            "reached and the furthest."
        ),
    )
    birthday_star: BirthdayStar | None = Field(
        None,
        description=(
            "stars: left out when no star's distance is within 2 "
            "light-years of the age."
        ),
    )
    stars: list[StarInfo] | None = Field(
        None, description="stars: nearest first, up to star_limit."
    )
    next_star: NextStar | None = Field(
        None,
        description="stars: left out once every star has been reached.",
    )

    estimated_exoplanets: int | None = Field(
        None, description="exoplanets: known exoplanets of the stars reached."
    )
    potentially_habitable: int | None = Field(
        None,
        description=(
            "exoplanets: an estimate of rocky planets in the conservative "
            "habitable zone, about 7% of them by Kepler's statistics."
        ),
    )

    star_type_breakdown: dict[str, int] | None = Field(
        None,
        description=(
            "star_classification: stars reached, by the spectral_class label."
        ),
    )

    planetary_ages: list[PlanetaryAge] | None = Field(
        None, description="planetary_ages: Mercury to Pluto."
    )

    body_stats: BodyStats | None = Field(None, description="body_stats.")

    cosmic_journey: CosmicJourney | None = Field(
        None, description="cosmic_journey."
    )

    scale_comparisons: list[ScaleComparison] | None = Field(
        None, description="scale_comparisons."
    )

    universe_age_percent: float | None = Field(
        None,
        description=(
            "universe_perspective: age as a percentage of the universe's, "
            "13.787 billion years."
        ),
    )

    sun_constellation: SunConstellation | None = Field(
        None, description="sun_constellation."
    )

    voyagers: list[VoyagerStatus] | None = Field(None, description="voyagers.")

    eclipses: EclipseCounts | None = Field(None, description="eclipses.")

    nasa_apod_url: str | None = Field(
        None,
        description=(
            "links: NASA's Astronomy Picture of the Day for the birthday, "
            "or APOD's front page for a day before 16 June 1995 or after "
            "15 June 2095."
        ),
    )
