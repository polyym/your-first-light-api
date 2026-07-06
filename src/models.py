"""Pydantic request/response schemas for the Your First Light API.

Defines the shared contract between the REST layer (``app``) and
the computation engine (``compute``).  Field-level descriptions
drive the auto-generated OpenAPI documentation.
"""

from typing import Literal, get_args

from pydantic import BaseModel, Field

# -------------------------------------------------------------------
# Category type
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# Error models (for OpenAPI documentation)
# -------------------------------------------------------------------
class ErrorResponse(BaseModel):
    """Returned for validation errors (422).

    Attributes:
        detail: Human-readable error message.
    """

    detail: str = Field(
        ...,
        description="Human-readable error message.",
        examples=["Invalid date: 'bad'. Expected YYYY-MM-DD."],
    )


class RateLimitResponse(BaseModel):
    """Returned when the client exceeds the rate limit (429).

    Attributes:
        detail: Retry-after message with remaining wait time.
    """

    detail: str = Field(
        ...,
        description="Retry-after message.",
        examples=[
            "Rate limited. Please wait 25.3 seconds "
            "before trying again.",
        ],
    )


# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------
class _BaseRequest(BaseModel):
    """Common fields shared by all date-format request variants.

    Subclasses override ``birthday`` and ``as_of`` with
    format-specific descriptions and examples.

    Attributes:
        categories: Optional list of category names to include in
            the response.  Omit to receive all categories.  An
            explicit empty list is rejected with a 422.
        star_limit: Maximum number of stars to return in the
            ``stars`` list (default 500).  Counts and
            ``next_star`` are always computed from the full
            catalogue.
    """

    categories: list[Category] | None = Field(
        None,
        description=(
            "Categories to include. Omit for all. "
            "Must not be empty when provided."
        ),
        min_length=1,
        max_length=15,
    )
    star_limit: int = Field(
        500,
        description=(
            "Maximum number of stars to return in the "
            "stars list. "
            "Counts and next_star are always complete. "
            "When truncated, stars_remaining shows how "
            "many additional stars were reached."
        ),
        ge=1,
        le=50000,
    )


class BigEndianRequest(_BaseRequest):
    """Birthday submitted as YYYY-MM-DD."""

    birthday: str = Field(
        ...,
        description="Date of birth in YYYY-MM-DD format",
        examples=["2002-10-14"],
        max_length=10,
    )
    as_of: str | None = Field(
        None,
        description=(
            "Reference date in YYYY-MM-DD "
            "(defaults to the current UTC date)."
        ),
        max_length=10,
    )


class MiddleEndianRequest(_BaseRequest):
    """Birthday submitted as MM/DD/YYYY."""

    birthday: str = Field(
        ...,
        description="Date of birth in MM/DD/YYYY format",
        examples=["10/14/2002"],
        max_length=10,
    )
    as_of: str | None = Field(
        None,
        description=(
            "Reference date in MM/DD/YYYY "
            "(defaults to the current UTC date)."
        ),
        max_length=10,
    )


class LittleEndianRequest(_BaseRequest):
    """Birthday submitted as DD/MM/YYYY."""

    birthday: str = Field(
        ...,
        description="Date of birth in DD/MM/YYYY format",
        examples=["14/10/2002"],
        max_length=10,
    )
    as_of: str | None = Field(
        None,
        description=(
            "Reference date in DD/MM/YYYY "
            "(defaults to the current UTC date)."
        ),
        max_length=10,
    )


# -------------------------------------------------------------------
# Response sub-models
# -------------------------------------------------------------------
class StarInfo(BaseModel):
    """A single star within the user's light sphere.

    Attributes:
        name: Common or catalogue name of the star.
        distance_ly: Distance from Earth in light-years.
        spectral_type: MK spectral classification code.
        spectral_class: Human-friendly star classification.
        apparent_magnitude: Visual brightness as seen from Earth.
        known_exoplanets: Confirmed exoplanet count.
        your_age_at_light_arrival_years: Age when birth-light
            first reached this star (equals ``distance_ly``).
        light_arrival_date: Calendar date of light arrival.
        naked_eye_visible: Whether the star is visible unaided.
        ra_deg: Right ascension in decimal degrees (J2000).
        dec_deg: Declination in decimal degrees (J2000).
        magnitude_band: Photometric band of
            ``apparent_magnitude`` (``"V"`` or ``"G"``), when
            known.
    """

    name: str
    distance_ly: float
    spectral_type: str
    spectral_class: str = Field(
        ..., description="Human-friendly star classification",
    )
    apparent_magnitude: float
    magnitude_band: str | None = Field(
        None,
        description=(
            "Photometric band of apparent_magnitude: 'V' "
            "(visual) or 'G' (Gaia broad-band, used when no "
            "V estimate exists). Omitted when unknown."
        ),
    )
    known_exoplanets: int
    your_age_at_light_arrival_years: float = Field(
        ...,
        description=(
            "Your age in years when light from your birth "
            "first reached this star (equals the star's "
            "distance in light-years)"
        ),
    )
    light_arrival_date: str = Field(
        ...,
        description=(
            "Calendar date (YYYY-MM-DD) when light from "
            "your birth first reached this star. Years "
            "are zero-padded to four digits; arrivals "
            "beyond year 9999 use five digits."
        ),
    )
    naked_eye_visible: bool
    ra_deg: float | None = Field(
        None,
        description="Right ascension (J2000, decimal degrees)",
    )
    dec_deg: float | None = Field(
        None,
        description="Declination (J2000, decimal degrees)",
    )


class NextStar(BaseModel):
    """The nearest star not yet reached by the user's light.

    Attributes:
        name: Name of the upcoming star.
        distance_ly: Distance from Earth in light-years.
        arrives_in_years: Years until the user's light reaches it.
        arrival_date: Predicted calendar date of arrival.
    """

    name: str
    distance_ly: float
    arrives_in_years: float
    arrival_date: str


class LightSphere(BaseModel):
    """Geometry of the user's expanding light sphere.

    Attributes:
        radius_ly: Radius in light-years (equals age in years).
        diameter_ly: Diameter in light-years.
        radius_km: Radius converted to kilometres.
        radius_au: Radius converted to astronomical units.
        volume_cubic_ly: Volume in cubic light-years.
        surface_area_sq_ly: Surface area in square light-years.
        milky_way_diameter_percent: Diameter as a percentage of
            the Milky Way's diameter.
        observable_universe_diameter_percent: Diameter as a
            percentage of the observable universe (93 billion ly).
    """

    radius_ly: float
    diameter_ly: float
    radius_km: float
    radius_au: float
    volume_cubic_ly: float
    surface_area_sq_ly: float
    milky_way_diameter_percent: float
    observable_universe_diameter_percent: float = Field(
        ...,
        description=(
            "Diameter of your sphere as a % of the "
            "observable universe (93 billion ly)"
        ),
    )


class PlanetaryAge(BaseModel):
    """The user's age expressed in another planet's orbital years.

    Attributes:
        planet: Planet name (e.g. ``"Mars"``).
        age: The user's age in that planet's years.
        orbital_period_earth_days: One year on that planet in
            Earth days.
    """

    planet: str
    age: float
    orbital_period_earth_days: float


class BodyStats(BaseModel):
    """Biological estimates over the user's lifetime.

    Attributes:
        estimated_heartbeats: Total heartbeats since birth.
        estimated_breaths: Total breaths since birth.
        estimated_blinks: Total blinks during waking hours.
        photons_emitted: Estimated infrared photons radiated
            (blackbody model at 310 K).
        thermal_power_watts: Net thermal radiation output in
            watts (body emission minus ambient absorption).
    """

    estimated_heartbeats: int
    estimated_breaths: int
    estimated_blinks: int
    photons_emitted: float = Field(
        ...,
        description=(
            "Estimated infrared photons radiated by your "
            "body since birth (blackbody model at 310K)"
        ),
    )
    thermal_power_watts: float = Field(
        ...,
        description=(
            "Net thermal radiation output: Stefan-Boltzmann "
            "blackbody emission at 310K (body) minus "
            "absorption at 293K (ambient ~20C). ~180W."
        ),
    )


class CosmicJourney(BaseModel):
    """How far the user has passively travelled through space.

    Attributes:
        earth_distance_around_sun_km: Distance Earth has orbited
            the Sun since birth.
        earth_orbits_completed: Number of full orbits completed.
        galactic_distance_km: Distance the Solar System has moved
            in its galactic orbit.
        galactic_orbit_degrees: Degrees traversed around the
            galactic centre.
        great_attractor_distance_km: Distance the Milky Way has
            moved toward the Great Attractor since birth.
        universe_expansion_percent: Percentage growth of the
            cosmological scale factor since birth (first-order
            Hubble expansion).
    """

    earth_distance_around_sun_km: float
    earth_orbits_completed: float
    galactic_distance_km: float
    galactic_orbit_degrees: float
    great_attractor_distance_km: float = Field(
        ...,
        description=(
            "How far the Milky Way has moved toward "
            "the Great Attractor since birth"
        ),
    )
    universe_expansion_percent: float = Field(
        ...,
        description=(
            "Percentage growth of the cosmological scale "
            "factor since birth (first-order Hubble "
            "expansion, H0 x age)"
        ),
    )


class ScaleComparison(BaseModel):
    """A single human-readable scale comparison.

    Attributes:
        label: Description of the comparison.
        value: Numeric value of the comparison.
        unit: Unit for the value (e.g. ``"trips"``, ``"years"``).
    """

    label: str
    value: float
    unit: str


class MoonPhaseAtBirth(BaseModel):
    """Lunar phase on the user's date of birth (midnight UTC).

    Attributes:
        phase_name: Human-readable phase (e.g. ``"Full Moon"``).
        illumination_percent: Illumination at midnight UTC.
        moon_age_days: Days into the lunar cycle (0 = New Moon).
    """

    phase_name: str = Field(
        ...,
        description=(
            "e.g. Waxing Crescent, Full Moon. "
            "Computed at midnight UTC on the birthday."
        ),
    )
    illumination_percent: float = Field(
        ...,
        description="Illumination at midnight UTC.",
    )
    moon_age_days: float = Field(
        ...,
        description=(
            "Days into the lunar cycle at midnight UTC "
            "(0 = New Moon)"
        ),
    )


class BirthdayStar(BaseModel):
    """The star whose distance best matches the user's age.

    Attributes:
        name: Name of the matching star.
        distance_ly: Distance from Earth in light-years.
        spectral_type: MK spectral classification code.
        difference_ly: Absolute distance mismatch from the
            user's age (0 = perfect match).
    """

    name: str = Field(
        ...,
        description=(
            "The star closest to your exact age in "
            "light-years — light leaving this star right "
            "now has been travelling since roughly the "
            "day you were born"
        ),
    )
    distance_ly: float
    spectral_type: str
    difference_ly: float = Field(
        ..., description="How close the match is (0 = perfect)",
    )


class SunConstellation(BaseModel):
    """Where the Sun actually was on the user's birthday.

    Attributes:
        constellation: IAU constellation containing the Sun at
            midnight UTC on the birthday.
        zodiac_sign: Traditional (tropical) astrological sign
            for the date.
        matches_zodiac_sign: Whether the two agree. Usually
            ``False``: roughly 2,000 years of axial precession
            has shifted the Sun's apparent path by about one
            constellation since the signs were fixed.
    """

    constellation: str = Field(
        ...,
        description=(
            "IAU constellation the Sun was actually in at "
            "midnight UTC on your birthday (one of 13, "
            "including Ophiuchus)."
        ),
    )
    zodiac_sign: str = Field(
        ...,
        description=(
            "Traditional (tropical) star sign for the date."
        ),
    )
    matches_zodiac_sign: bool = Field(
        ...,
        description=(
            "Whether the actual constellation matches the "
            "sign. Usually false, thanks to ~2,000 years of "
            "axial precession."
        ),
    )


class VoyagerStatus(BaseModel):
    """Distance a Voyager probe has covered since the user's birth.

    Attributes:
        name: Probe name (``"Voyager 1"`` or ``"Voyager 2"``).
        launch_date: ISO-format launch date.
        distance_travelled_since_birth_km: Distance in km.
        distance_travelled_since_birth_au: Distance in AU.
        speed_km_s: Current heliocentric speed in km/s.
        was_launched_before_birth: Whether the probe launched
            before the user was born.
    """

    name: str
    launch_date: str
    distance_travelled_since_birth_km: float
    distance_travelled_since_birth_au: float
    speed_km_s: float
    was_launched_before_birth: bool


class EclipseCounts(BaseModel):
    """Eclipse counts over the user's lifetime (NASA catalogue).

    Attributes:
        solar_eclipses: Number of solar eclipses.
        lunar_eclipses: Number of lunar eclipses.
        total_eclipses: Combined count (solar + lunar).
        next_solar_eclipse: Date of the first solar eclipse
            strictly after the reference date.
        next_lunar_eclipse: Date of the first lunar eclipse
            strictly after the reference date.
        coverage_note: Present only when the date range extends
            outside the catalogue's 1900–2100 window.
    """

    solar_eclipses: int
    lunar_eclipses: int
    total_eclipses: int
    next_solar_eclipse: str | None = Field(
        None,
        description=(
            "Date (YYYY-MM-DD) of the first solar eclipse "
            "strictly after as_of. Omitted when as_of is "
            "beyond the catalogue window (2100)."
        ),
    )
    next_lunar_eclipse: str | None = Field(
        None,
        description=(
            "Date (YYYY-MM-DD) of the first lunar eclipse "
            "strictly after as_of. Omitted when as_of is "
            "beyond the catalogue window (2100)."
        ),
    )
    coverage_note: str | None = Field(
        None,
        description=(
            "Present when the date range extends outside "
            "the eclipse catalogue (1900-2100). Counts "
            "only reflect eclipses within the covered "
            "period."
        ),
    )


# -------------------------------------------------------------------
# Top-level response
# -------------------------------------------------------------------
class FirstLightResponse(BaseModel):
    """Full API response.  Only requested categories are populated.

    All category-specific fields default to ``None`` and are
    excluded from the JSON response via
    ``response_model_exclude_none=True``.  A field is therefore
    omitted both when its category was not requested AND when
    it has no value within a requested category (for example
    ``birthday_star`` when no star matches within tolerance,
    ``next_star`` when every catalogued star has been reached,
    or ``stars_remaining`` when the list was not truncated).
    The ``birthday`` and ``as_of`` fields are always present.
    """

    model_config = {
        "json_schema_extra": {
            "description": (
                "All category fields are optional. Only "
                "requested categories are populated, and a "
                "field is also omitted when it has no value "
                "within a requested category (e.g. "
                "birthday_star with no match, next_star when "
                "all stars are reached)."
            ),
        },
    }

    # Always included
    birthday: str
    as_of: str

    # time_alive
    age_years: float | None = None
    age_days: int | None = None
    age_hours: int | None = None
    age_minutes: int | None = None
    age_seconds: int | None = None
    earth_rotations: float | None = Field(
        None,
        description=(
            "Sidereal rotations of Earth since birth "
            "(slightly more than solar days)"
        ),
    )
    leap_years_lived_through: int | None = None

    # moon
    moon_phase_at_midnight_utc: MoonPhaseAtBirth | None = None
    full_moons_since_birth: int | None = None
    next_full_moon_date: str | None = Field(
        None,
        description=(
            "Date (YYYY-MM-DD) of the first full moon on "
            "or after as_of, from the same mean synodic "
            "model as the full-moon count (the modelled "
            "instant can differ from the true instant by "
            "a few hours)."
        ),
    )

    # light_sphere
    light_sphere: LightSphere | None = None
    speed_of_light_km_s: float | None = None

    # stars
    stars_reached: int | None = None
    naked_eye_stars_reached: int | None = None
    stars_reached_this_year: int | None = Field(
        None,
        description=(
            "Catalogue stars your birth light reached in "
            "the 365.25 days up to as_of."
        ),
    )
    stars_remaining: str | None = Field(
        None,
        description=(
            "Human-readable message indicating how many "
            "additional reached stars were omitted and "
            "the name of the furthest star reached. "
            "Only present when the list was truncated."
        ),
    )
    birthday_star: BirthdayStar | None = Field(
        None,
        description=(
            "The star whose distance most closely "
            "matches your age in light-years. Omitted "
            "when no star is within 2 light-years of "
            "your age."
        ),
    )
    stars: list[StarInfo] | None = None
    next_star: NextStar | None = Field(
        None,
        description=(
            "The nearest star your light has not yet "
            "reached. Omitted when every star in the "
            "catalogue has been reached."
        ),
    )

    # exoplanets
    estimated_exoplanets: int | None = None
    potentially_habitable: int | None = Field(
        None,
        description=(
            "Estimated habitable-zone rocky planets "
            "within your light sphere. Derived as ~7% "
            "of known exoplanets, based on Kepler "
            "mission statistics for rocky planets in "
            "the conservative habitable zone."
        ),
    )

    # star_classification
    star_type_breakdown: dict[str, int] | None = None

    # planetary_ages
    planetary_ages: list[PlanetaryAge] | None = None

    # body_stats
    body_stats: BodyStats | None = None

    # cosmic_journey
    cosmic_journey: CosmicJourney | None = None

    # scale_comparisons
    scale_comparisons: list[ScaleComparison] | None = None

    # universe_perspective
    universe_age_percent: float | None = Field(
        None,
        description=(
            "Your age as a percentage of the "
            "universe's age (13.787 billion years)"
        ),
    )

    # sun_constellation
    sun_constellation: SunConstellation | None = None

    # voyagers
    voyagers: list[VoyagerStatus] | None = None

    # eclipses
    eclipses: EclipseCounts | None = None

    # links
    nasa_apod_url: str | None = Field(
        None,
        description=(
            "NASA Astronomy Picture of the Day "
            "for this birthday"
        ),
    )
