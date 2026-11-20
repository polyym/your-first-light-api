"""What clients, above all the UI, rely on from the real app and data."""

import re
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from first_light.app import app
from first_light.web import rate_limit

BIG_ENDIAN = "/v1/big-endian-first-light"
MIDDLE_ENDIAN = "/v1/middle-endian-first-light"
LITTLE_ENDIAN = "/v1/little-endian-first-light"
ORIGIN = {"Origin": "https://example.org"}
UI_REQUEST = {"birthday": "1997-03-15", "star_limit": 500}
LINKS_ONLY = {
    "birthday": "1998-11-15",
    "as_of": "2026-11-18",
    "categories": ["links"],
}

# The patterns the UI matches: an ISO date, the first number in a 429
# detail, the date message and the bracketed class letter.
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
FIRST_NUMBER = re.compile(r"\d+(?:\.\d+)?")
UI_MAX_WAIT_SECONDS = 60
DATE_PROBLEM = re.compile(r"future|invalid|birthday", re.IGNORECASE)
CLASS_LABEL = re.compile(r"[^()]+ \([A-Z]\)")
UNKNOWN_CLASS = "Unknown"

FIELDS_THE_UI_READS = {
    "time_alive": ("age_days", "age_seconds"),
    "moon": (
        "moon_phase_at_midnight_utc",
        "full_moons_since_birth",
        "next_full_moon_date",
    ),
    "light_sphere": ("light_sphere",),
    "stars": (
        "stars",
        "stars_reached",
        "naked_eye_stars_reached",
        "stars_reached_this_year",
        "birthday_star",
        "next_star",
    ),
    "exoplanets": ("estimated_exoplanets", "potentially_habitable"),
    "star_classification": ("star_type_breakdown",),
    "planetary_ages": ("planetary_ages",),
    "body_stats": ("body_stats",),
    "cosmic_journey": ("cosmic_journey",),
    "scale_comparisons": ("scale_comparisons",),
    "universe_perspective": ("universe_age_percent",),
    "voyagers": ("voyagers",),
    "eclipses": ("eclipses",),
    "links": ("nasa_apod_url",),
    "sun_constellation": ("sun_constellation",),
}
# The fields the UI reads inside each object, or each object of a list,
# with the JSON type its code takes them to be; float stands for any
# number.
OBJECT_FIELDS_THE_UI_READS: dict[str, dict[str, type]] = {
    "moon_phase_at_midnight_utc": {
        "phase_name": str,
        "illumination_percent": float,
        "moon_age_days": float,
    },
    "light_sphere": {
        "radius_ly": float,
        "diameter_ly": float,
        "radius_au": float,
        "volume_cubic_ly": float,
        "milky_way_diameter_percent": float,
    },
    "stars": {
        "spectral_type": str,
        "known_exoplanets": float,
        "your_age_at_light_arrival_years": float,
        "naked_eye_visible": bool,
    },
    "birthday_star": {
        "name": str,
        "distance_ly": float,
        "difference_ly": float,
    },
    "next_star": {"name": str, "distance_ly": float, "arrival_date": str},
    "planetary_ages": {
        "planet": str,
        "age": float,
        "orbital_period_earth_days": float,
    },
    "body_stats": {
        "estimated_heartbeats": float,
        "estimated_breaths": float,
        "estimated_blinks": float,
        "photons_emitted": float,
        "thermal_power_watts": float,
    },
    "cosmic_journey": {
        "earth_distance_around_sun_km": float,
        "earth_orbits_completed": float,
        "galactic_distance_km": float,
    },
    "scale_comparisons": {"label": str, "value": float},
    "sun_constellation": {"constellation": str, "zodiac_sign": str},
    "voyagers": {
        "name": str,
        "distance_travelled_since_birth_km": float,
        "distance_travelled_since_birth_au": float,
        "speed_km_s": float,
    },
    "eclipses": {
        "solar_eclipses": float,
        "lunar_eclipses": float,
        "total_eclipses": float,
    },
}


class _FrozenClock:
    """Stands in for the time module inside the rate limiter."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FrozenClock:
    """Holds the rate limiter's clock still until a test moves it."""
    frozen = _FrozenClock()
    monkeypatch.setattr(rate_limit, "time", frozen)
    return frozen


@pytest.fixture(scope="module")
def ui_response() -> Response:
    """The answer to the UI's own request, sent once for the module."""
    return TestClient(app).post(BIG_ENDIAN, json=UI_REQUEST, headers=ORIGIN)


@pytest.fixture(scope="module")
def ui_body(ui_response: Response) -> dict[str, Any]:
    """The JSON body of the answer to the UI's own request."""
    body: dict[str, Any] = ui_response.json()
    return body


def _wait_read_by_ui(response: Response) -> float:
    match = FIRST_NUMBER.search(response.json()["detail"])
    assert match is not None
    return float(match.group())


def _is_json_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_drawable_star(star: dict[str, Any]) -> bool:
    return (
        isinstance(star.get("name"), str)
        and _is_json_number(star.get("distance_ly"))
        and _is_json_number(star.get("apparent_magnitude"))
        and isinstance(star.get("spectral_class"), str)
        and _is_iso_date(star.get("light_arrival_date"))
    )


@pytest.mark.parametrize(
    "path",
    [BIG_ENDIAN, MIDDLE_ENDIAN, LITTLE_ENDIAN],
    ids=["big-endian", "middle-endian", "little-endian"],
)
def test_preflight_from_another_origin_allows_a_json_post(
    client: TestClient, path: str
) -> None:
    response = client.options(
        path,
        headers={
            **ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    methods = response.headers["access-control-allow-methods"].split(",")
    assert "POST" in [method.strip() for method in methods]
    headers = response.headers["access-control-allow-headers"].split(",")
    assert "content-type" in [header.strip().lower() for header in headers]


@pytest.mark.parametrize(
    ("bodies", "status"),
    [
        ([LINKS_ONLY], 200),
        ([{"birthday": "bad"}], 422),
        ([LINKS_ONLY, LINKS_ONLY], 429),
        ([{"birthday": "x" * 70_000}], 413),
    ],
    ids=["ok", "unprocessable", "rate-limited", "too-large"],
)
def test_post_answer_allows_any_origin(
    client: TestClient, bodies: list[dict[str, Any]], status: int
) -> None:
    for body in bodies:
        response = client.post(BIG_ENDIAN, json=body, headers=ORIGIN)

    assert response.status_code == status
    assert response.headers["access-control-allow-origin"] == "*"


def test_first_number_in_429_detail_is_the_wait_left(
    client: TestClient, clock: _FrozenClock
) -> None:
    client.post(BIG_ENDIAN, json=LINKS_ONLY)
    clock.now += 4.75

    response = client.post(BIG_ENDIAN, json=LINKS_ONLY)

    assert response.status_code == 429
    assert _wait_read_by_ui(response) == 25.3


def test_429_wait_stays_within_the_ui_clamp(
    client: TestClient, clock: _FrozenClock
) -> None:
    client.post(BIG_ENDIAN, json=LINKS_ONLY)

    response = client.post(BIG_ENDIAN, json=LINKS_ONLY)

    assert response.status_code == 429
    assert _wait_read_by_ui(response) <= UI_MAX_WAIT_SECONDS


def test_retry_after_the_wait_read_from_a_429_succeeds(
    client: TestClient, clock: _FrozenClock
) -> None:
    client.post(BIG_ENDIAN, json=LINKS_ONLY)
    clock.now += 4.75
    refused = client.post(BIG_ENDIAN, json=LINKS_ONLY)
    clock.now += _wait_read_by_ui(refused)

    assert client.post(BIG_ENDIAN, json=LINKS_ONLY).status_code == 200


@pytest.mark.parametrize(
    "request_args",
    [
        {"content": b"{nope", "headers": {"Content-Type": "application/json"}},
        {"content": b"{}", "headers": {"Content-Type": "text/plain"}},
        {"json": {"birthday": "1998-11-15", "star_limit": 0}},
        {"json": {"birthday": "15/11/1998"}},
        {"json": {"birthday": "2026-11-18", "as_of": "2026-11-18"}},
    ],
    ids=[
        "not-json",
        "not-declared-json",
        "field-out-of-range",
        "date-that-does-not-parse",
        "birthday-not-in-the-past",
    ],
)
def test_unprocessable_answer_is_one_plain_detail(
    client: TestClient, request_args: dict[str, Any]
) -> None:
    response = client.post(BIG_ENDIAN, **request_args)

    assert response.status_code == 422
    body = response.json()
    assert list(body) == ["detail"]
    assert isinstance(body["detail"], str)


@pytest.mark.parametrize(
    "payload",
    [
        {"birthday": "bad"},
        {"birthday": "1998-02-30"},
        {"birthday": "2030-01-01", "as_of": "2026-11-18"},
        {"birthday": "2026-11-18", "as_of": "2026-11-18"},
        {"birthday": "1998-11-15", "as_of": "15/11/2026"},
        {"birthday": "1998-11-15", "as_of": ""},
        {"as_of": "2026-11-18"},
        {"birthday": 19981115},
        {"birthday": "1998-11-15T00"},
    ],
    ids=[
        "not-a-date",
        "impossible-day",
        "birthday-in-the-future",
        "birthday-on-as-of",
        "as-of-in-another-format",
        "empty-as-of",
        "birthday-missing",
        "birthday-a-number",
        "birthday-too-long",
    ],
)
def test_date_problem_gets_the_ui_date_message(
    client: TestClient, payload: dict[str, Any]
) -> None:
    response = client.post(BIG_ENDIAN, json=payload)

    assert response.status_code == 422
    assert DATE_PROBLEM.search(response.json()["detail"])


def test_ui_request_succeeds(ui_response: Response) -> None:
    assert ui_response.status_code == 200


@pytest.mark.parametrize("category", list(FIELDS_THE_UI_READS))
def test_ui_request_gets_every_category(
    ui_body: dict[str, Any], category: str
) -> None:
    missing = [
        field for field in FIELDS_THE_UI_READS[category] if field not in ui_body
    ]
    assert missing == []


@pytest.mark.parametrize("name", list(OBJECT_FIELDS_THE_UI_READS))
def test_ui_request_gets_every_field_the_ui_reads_inside_an_object(
    ui_body: dict[str, Any], name: str
) -> None:
    value = ui_body[name]
    objects = value if isinstance(value, list) else [value]
    wrong = [
        (index, field)
        for index, item in enumerate(objects)
        for field, kind in OBJECT_FIELDS_THE_UI_READS[name].items()
        if not (
            _is_json_number(item.get(field))
            if kind is float
            else isinstance(item.get(field), kind)
        )
    ]
    assert objects
    assert wrong == []


def test_ui_request_lists_stars_the_ui_can_draw(
    ui_body: dict[str, Any],
) -> None:
    stars = ui_body["stars"]
    assert stars
    assert [star for star in stars if not _is_drawable_star(star)] == []


def test_ui_request_lists_the_stars_reached_up_to_its_limit(
    ui_body: dict[str, Any],
) -> None:
    # The request has no as_of, so the count grows with today's date and
    # passes the UI's limit in time.
    listed = min(ui_body["stars_reached"], UI_REQUEST["star_limit"])
    assert len(ui_body["stars"]) == listed
    assert ("stars_remaining" in ui_body) == (ui_body["stars_reached"] > listed)


def test_listed_stars_were_reached_by_as_of(ui_body: dict[str, Any]) -> None:
    as_of = date.fromisoformat(ui_body["as_of"])
    late = [
        star["name"]
        for star in ui_body["stars"]
        if date.fromisoformat(star["light_arrival_date"]) > as_of
    ]
    assert late == []


def test_next_star_is_reached_on_or_after_as_of(
    ui_body: dict[str, Any],
) -> None:
    arrival = date.fromisoformat(ui_body["next_star"]["arrival_date"])
    assert arrival >= date.fromisoformat(ui_body["as_of"])


@pytest.mark.parametrize(
    "path",
    [
        ("as_of",),
        ("next_star", "arrival_date"),
        ("next_full_moon_date",),
        ("eclipses", "next_solar_eclipse"),
        ("eclipses", "next_lunar_eclipse"),
    ],
    ids=lambda path: ".".join(path),
)
def test_dates_the_ui_parses_are_iso_dates(
    ui_body: dict[str, Any], path: tuple[str, ...]
) -> None:
    value: Any = ui_body
    for key in path:
        value = value[key]
    assert _is_iso_date(value)


def test_every_star_class_carries_a_capital_letter_in_brackets(
    ui_body: dict[str, Any],
) -> None:
    unlettered = [
        (star["name"], star["spectral_class"])
        for star in ui_body["stars"]
        if not CLASS_LABEL.fullmatch(star["spectral_class"])
        and not (
            star["spectral_class"] == UNKNOWN_CLASS
            and star["spectral_type"] == ""
        )
    ]
    assert unlettered == []


def test_every_class_breakdown_label_carries_a_capital_letter_in_brackets(
    client: TestClient,
) -> None:
    every_star = {
        "birthday": "0001-01-01",
        "as_of": "2026-11-18",
        "categories": ["star_classification"],
    }

    response = client.post(BIG_ENDIAN, json=every_star)

    labels = response.json()["star_type_breakdown"]
    assert [
        label
        for label in labels
        if label != UNKNOWN_CLASS and not CLASS_LABEL.fullmatch(label)
    ] == []


@pytest.mark.parametrize(
    ("needle", "value"),
    [
        ("car", 604_558_889.43),
        ("jet", 67_173_209.94),
        ("voyager", 987_841.32),
        ("earth", 7.194592403618936e31),
    ],
    ids=["car", "jet", "voyager", "earths"],
)
def test_ui_finds_each_scale_row_by_its_word(
    client: TestClient, needle: str, value: float
) -> None:
    rows = client.post(
        BIG_ENDIAN,
        json={
            "birthday": "1998-11-15",
            "as_of": "2026-11-18",
            "categories": ["scale_comparisons"],
        },
    ).json()["scale_comparisons"]

    first = next(row for row in rows if needle in row["label"].lower())

    assert first["value"] == value


def test_scale_labels_name_car_jet_voyager_and_earths_in_that_order(
    ui_body: dict[str, Any],
) -> None:
    words = ("car", "jet", "Voyager", "Earths")
    named = [
        word
        for row in ui_body["scale_comparisons"]
        for word in words
        if word in row["label"]
    ]
    assert named == list(words)


def test_planets_run_from_mercury_to_pluto(ui_body: dict[str, Any]) -> None:
    assert [row["planet"] for row in ui_body["planetary_ages"]] == [
        "Mercury",
        "Venus",
        "Earth",
        "Mars",
        "Jupiter",
        "Saturn",
        "Uranus",
        "Neptune",
        "Pluto",
    ]


def test_voyagers_are_named_voyager_1_and_voyager_2(
    ui_body: dict[str, Any],
) -> None:
    assert [row["name"] for row in ui_body["voyagers"]] == [
        "Voyager 1",
        "Voyager 2",
    ]
