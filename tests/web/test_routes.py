"""Tests for the index, the health check and the three POST endpoints."""

import asyncio
import json
import queue
import threading
from datetime import UTC, date, datetime, timedelta

import pytest
from starlette.routing import Match

from first_light.app import app
from first_light.constants import API_VERSION
from first_light.facts import stars
from first_light.facts.catalogues import DATA_DIR
from first_light.models import (
    BigEndianRequest,
    FirstLightResponse,
    LittleEndianRequest,
    MiddleEndianRequest,
)
from first_light.web import routes

BIG = "/v1/big-endian-first-light"
MIDDLE = "/v1/middle-endian-first-light"
LITTLE = "/v1/little-endian-first-light"
PREFLIGHT = {
    "Origin": "https://example.org",
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
}
EVERY_CATEGORY = {
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
}
# The recorded response to the README's example request.
README_EXAMPLE_BODY = (
    b'{"birthday":"1998-11-15","as_of":"2026-04-11","age_years":27.4,'
    b'"age_days":10009,"age_hours":240216,"age_minutes":14412960,'
    b'"age_seconds":864777606,"earth_rotations":10036.4,'
    b'"leap_years_lived_through":7,'
    b'"nasa_apod_url":"https://apod.nasa.gov/apod/ap981115.html"}'
)
# The recorded response to an eclipses request for 1988-03-21 to
# 2026-11-18.
ECLIPSES_BODY = (
    b'{"birthday":"1988-03-21","as_of":"2026-11-18","eclipses":'
    b'{"solar_eclipses":84,"lunar_eclipses":87,"total_eclipses":171,'
    b'"next_solar_eclipse":"2027-02-06","next_lunar_eclipse":"2027-02-20"}}'
)
# Copies of four shipped entries, out of distance order. The monthly
# data refresh can change the shipped catalogue, so the stars request
# below runs on these copies alone.
NEIGHBOURS = [
    {
        "name": "Wolf 359",
        "distance_ly": 7.8558,
        "spectral_type": "M6.5Ve",
        "apparent_magnitude": 13.54,
        "magnitude_band": "V",
        "known_exoplanets": 0,
        "ra_deg": 164.1205,
        "dec_deg": 7.0147,
    },
    {
        "name": "Barnard's Star",
        "distance_ly": 5.9577,
        "spectral_type": "M4.0V",
        "apparent_magnitude": 9.51,
        "magnitude_band": "V",
        "known_exoplanets": 4,
        "ra_deg": 269.4521,
        "dec_deg": 4.6934,
    },
    {
        "name": "Alpha Centauri A",
        "distance_ly": 4.365,
        "spectral_type": "G2V",
        "apparent_magnitude": -0.01,
        "magnitude_band": "V",
        "known_exoplanets": 0,
        "ra_deg": 219.9021,
        "dec_deg": -60.834,
    },
    {
        "name": "Proxima Centauri",
        "distance_ly": 4.2465,
        "spectral_type": "M5.5Ve",
        "apparent_magnitude": 11.13,
        "magnitude_band": "V",
        "known_exoplanets": 2,
        "ra_deg": 217.4289,
        "dec_deg": -62.6795,
    },
]
# The recorded response, given NEIGHBOURS as the catalogue, to a stars
# request for 2020-01-01 to 2026-11-18 with a star_limit of 2.
NEIGHBOURS_BODY = (
    b'{"birthday":"2020-01-01","as_of":"2026-11-18","stars_reached":3,'
    b'"naked_eye_stars_reached":1,"stars_reached_this_year":1,'
    b'"stars_remaining":"Your light has reached 1 more star, with the '
    b"furthest being Barnard's Star.\","
    b'"birthday_star":{"name":"Barnard\'s Star","distance_ly":5.96,'
    b'"spectral_type":"M4.0V","difference_ly":0.92},'
    b'"stars":[{"name":"Proxima Centauri","distance_ly":4.25,'
    b'"spectral_type":"M5.5Ve","spectral_class":"Red dwarf (M)",'
    b'"apparent_magnitude":11.13,"magnitude_band":"V","known_exoplanets":2,'
    b'"your_age_at_light_arrival_years":4.25,'
    b'"light_arrival_date":"2024-03-31","naked_eye_visible":false,'
    b'"ra_deg":217.4289,"dec_deg":-62.6795},'
    b'{"name":"Alpha Centauri A","distance_ly":4.37,"spectral_type":"G2V",'
    b'"spectral_class":"Sun-like (G)","apparent_magnitude":-0.01,'
    b'"magnitude_band":"V","known_exoplanets":0,'
    b'"your_age_at_light_arrival_years":4.37,'
    b'"light_arrival_date":"2024-05-13","naked_eye_visible":true,'
    b'"ra_deg":219.9021,"dec_deg":-60.834}],'
    b'"next_star":{"name":"Wolf 359","distance_ly":7.86,'
    b'"arrives_in_years":0.98,"arrival_date":"2027-11-09"}}'
)
STAR = {"name": "Proxima Centauri", "distance_ly": 4.2465}
# Ample for a pool thread to pick up work on a loaded machine, and the
# longest a stand-in computation blocks, so that a failure cannot hang
# the pool for later tests.
WAIT_LIMIT_SECONDS = 5
# How long a third computation, which must queue, is given to start
# anyway.
SETTLE_SECONDS = 0.3
CONCURRENT_BIRTHDAYS = ("2001-01-01", "2002-02-02", "2003-03-03")
MANIFEST = {
    "files": {
        "eclipses.json": {"entries": 913, "updated": "2026-07-06"},
        "stars.json": {"entries": 49413, "updated": "2026-09-06"},
    }
}


@pytest.fixture
def catalogues(monkeypatch):
    """Replaces the catalogues /health reads with synthetic ones."""

    def install(stars, eclipses, manifest=MANIFEST):
        monkeypatch.setattr(routes, "NEARBY_STARS", [STAR] * stars)
        monkeypatch.setattr(
            routes, "SOLAR_ECLIPSE_DATES", (date(2024, 4, 8),) * eclipses
        )
        monkeypatch.setattr(routes, "DATA_MANIFEST", manifest)

    return install


@pytest.fixture
def compute_calls(monkeypatch):
    """Records what the endpoints pass to compute_first_light."""
    calls = []

    def record(birth, as_of, categories, star_limit):
        calls.append((birth, as_of, categories, star_limit))
        return FirstLightResponse(
            birthday=birth.isoformat(), as_of=as_of.isoformat()
        )

    monkeypatch.setattr(routes, "compute_first_light", record)
    return calls


def test_index_names_the_api_and_its_endpoints(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "name": "Your First Light",
        "version": API_VERSION,
        "description": "Post your birthday. Discover your cosmic reach.",
        "docs_url": "/docs",
        "health_url": "/health",
        "endpoints": [BIG, LITTLE, MIDDLE],
    }


def test_index_points_at_the_served_docs(client):
    docs_url = client.get("/").json()["docs_url"]
    assert client.get(docs_url).status_code == 200


def test_schema_is_named_and_versioned_as_the_index(client):
    index = client.get("/").json()
    assert client.get("/openapi.json").json()["info"] == {
        "title": index["name"],
        "description": index["description"],
        "version": index["version"],
    }


@pytest.mark.parametrize("path", ["/", "/health"])
def test_head_answers_like_get_without_a_body(client, path):
    get = client.get(path)
    head = client.head(path)
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-type"] == "application/json"
    assert head.headers["content-length"] == str(len(get.content))


@pytest.mark.parametrize("path", ["/", "/health"])
def test_index_and_health_refuse_post_naming_get_and_head(client, path):
    response = client.post(path)
    assert response.status_code == 405
    assert set(response.headers["allow"].split(", ")) == {"GET", "HEAD"}
    assert response.json() == {"detail": "Method Not Allowed"}


@pytest.mark.parametrize(
    ("stars", "eclipses", "status_code", "status"),
    [
        (1, 2, 200, "ok"),
        (2, 1, 200, "ok"),
        (0, 2, 503, "degraded"),
        (2, 0, 503, "degraded"),
    ],
    ids=["one-star", "one-eclipse", "no-stars", "no-eclipses"],
)
def test_health_is_503_when_a_catalogue_is_empty(
    client, catalogues, stars, eclipses, status_code, status
):
    catalogues(stars, eclipses)
    response = client.get("/health")
    assert response.status_code == status_code
    body = response.json()
    assert (body["status"], body["stars_loaded"], body["eclipses_loaded"]) == (
        status,
        stars,
        eclipses,
    )


def test_health_counts_the_solar_eclipses_in_the_shipped_catalogue(client):
    """Only the solar list is counted, as clients already read it."""
    eclipses = json.loads(
        (DATA_DIR / "eclipses.json").read_text(encoding="utf-8")
    )
    assert client.get("/health").json()["eclipses_loaded"] == len(
        eclipses["solarEclipses"]
    )


def test_head_health_is_503_when_a_catalogue_is_empty(client, catalogues):
    catalogues(0, 2)
    assert client.head("/health").status_code == 503


def test_health_gives_the_date_each_data_file_changed(client, catalogues):
    catalogues(3, 2)
    assert client.get("/health").json() == {
        "status": "ok",
        "stars_loaded": 3,
        "eclipses_loaded": 2,
        "data_updated": {
            "eclipses.json": "2026-07-06",
            "stars.json": "2026-09-06",
        },
    }


@pytest.mark.parametrize(
    "manifest", [{}, {"files": {}}], ids=["no-manifest", "no-files"]
)
def test_health_leaves_out_data_updated_without_a_manifest(
    client, catalogues, manifest
):
    catalogues(3, 2, manifest)
    assert "data_updated" not in client.get("/health").json()


def test_schema_documents_get_only_for_index_and_health(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {path: sorted(item) for path, item in paths.items()} == {
        "/": ["get"],
        "/health": ["get"],
        BIG: ["post"],
        MIDDLE: ["post"],
        LITTLE: ["post"],
    }


def test_schema_documents_both_health_answers(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert sorted(paths["/health"]["get"]["responses"]) == ["200", "503"]


@pytest.mark.parametrize("path", [BIG, MIDDLE, LITTLE])
def test_schema_documents_every_answer_to_a_post(client, path):
    schema = client.get("/openapi.json").json()
    documented = schema["paths"][path]["post"]["responses"]

    assert {
        status: (
            answer["content"]["application/json"]["schema"]["$ref"],
            answer["description"],
        )
        for status, answer in documented.items()
    } == {
        "200": (
            "#/components/schemas/FirstLightResponse",
            "Successful Response",
        ),
        "400": (
            "#/components/schemas/ErrorResponse",
            "A body that cannot be decoded, such as invalid UTF-8.",
        ),
        "413": (
            "#/components/schemas/ErrorResponse",
            "A body larger than 64 KB.",
        ),
        "422": (
            "#/components/schemas/ErrorResponse",
            "A date that does not parse, a birthday that is not before "
            "as_of (today when it is left out), or another invalid field.",
        ),
        "429": (
            "#/components/schemas/RateLimitResponse",
            "Rate limited: one successful request every 30 s for each caller.",
        ),
        "500": (
            "#/components/schemas/ErrorResponse",
            "An unexpected server error.",
        ),
    }
    assert documented["429"]["headers"] == {
        "Retry-After": {
            "description": "The wait in whole seconds.",
            "schema": {"type": "integer"},
        }
    }


def test_schema_names_each_post_endpoint_by_its_date_format(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        path: paths[path]["post"]["summary"] for path in (BIG, MIDDLE, LITTLE)
    } == {
        BIG: "Birthday as YYYY-MM-DD",
        MIDDLE: "Birthday as MM/DD/YYYY",
        LITTLE: "Birthday as DD/MM/YYYY",
    }


@pytest.mark.parametrize("path", [BIG, MIDDLE, LITTLE])
def test_request_the_docs_offer_to_send_is_accepted(client, path):
    """A schema with no example would offer "string" as as_of."""
    document = client.get("/openapi.json").json()
    body = document["paths"][path]["post"]["requestBody"]["content"]
    name = body["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]
    (example,) = document["components"]["schemas"][name]["examples"]

    assert set(example) == {"birthday"}
    assert client.post(path, json=example).status_code == 200


@pytest.mark.parametrize("path", [BIG, MIDDLE, LITTLE])
def test_post_paths_refuse_get(client, path):
    response = client.get(path)
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert response.json() == {"detail": "Method Not Allowed"}


@pytest.mark.parametrize("root_path", ["", "/x", "/x/", "/v1"])
@pytest.mark.parametrize("path", [BIG, MIDDLE, LITTLE])
def test_limits_count_exactly_the_paths_the_router_serves(path, root_path):
    """Starlette also serves a path with one newline after it.

    It takes a server's root path off the front of a path as well,
    before it matches.
    """
    variants = [path + chr(code) for code in range(128)]
    variants += [path, path + "\n\n", "\n" + path, path.upper()]
    variants += [root_path + variant for variant in variants]
    variants += [root_path, root_path + root_path + path, root_path + path[1:]]

    for variant in variants:
        scope = {
            "type": "http",
            "method": "POST",
            "path": variant,
            "root_path": root_path,
        }
        served = any(
            route.matches(scope)[0] is Match.FULL for route in app.routes
        )
        counted = routes.routed_path(scope) in routes.FIRST_LIGHT_PATHS
        assert served == counted, (root_path, variant)


@pytest.mark.parametrize("path", [BIG, MIDDLE, LITTLE])
def test_browser_preflight_for_a_json_post_succeeds(client, path):
    response = client.options(path, headers=PREFLIGHT)
    assert response.status_code == 200
    assert {
        name: response.headers.get(name)
        for name in (
            "access-control-allow-origin",
            "access-control-allow-methods",
            "access-control-allow-headers",
            "access-control-max-age",
        )
    } == {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": (
            "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY"
        ),
        "access-control-allow-headers": "content-type",
        "access-control-max-age": "600",
    }


@pytest.mark.parametrize(
    ("path", "birthday", "as_of"),
    [
        (BIG, "1998-11-15", "2026-04-11"),
        (MIDDLE, "11/15/1998", "04/11/2026"),
        (LITTLE, "15/11/1998", "11/04/2026"),
    ],
    ids=["big-endian", "middle-endian", "little-endian"],
)
def test_same_date_in_each_format_gives_the_same_body(
    client, path, birthday, as_of
):
    response = client.post(
        path,
        json={
            "birthday": birthday,
            "as_of": as_of,
            "categories": ["time_alive", "links"],
        },
    )
    assert response.status_code == 200
    assert response.content == README_EXAMPLE_BODY


def test_eclipses_body_matches_the_recording_byte_for_byte(client):
    response = client.post(
        BIG,
        json={
            "birthday": "1988-03-21",
            "as_of": "2026-11-18",
            "categories": ["eclipses"],
        },
    )
    assert response.content == ECLIPSES_BODY


def test_stars_body_matches_the_recording_byte_for_byte(client, monkeypatch):
    monkeypatch.setattr(stars, "NEARBY_STARS", NEIGHBOURS)
    response = client.post(
        BIG,
        json={
            "birthday": "2020-01-01",
            "as_of": "2026-11-18",
            "categories": ["stars"],
            "star_limit": 2,
        },
    )
    assert response.content == NEIGHBOURS_BODY


@pytest.mark.parametrize(
    ("path", "birthday", "as_of"),
    [
        (BIG, "1998-11-15", "2026-04-11"),
        (MIDDLE, "11/15/1998", "04/11/2026"),
        (LITTLE, "15/11/1998", "11/04/2026"),
    ],
    ids=["big-endian", "middle-endian", "little-endian"],
)
def test_endpoint_passes_the_request_on_to_compute(
    client, compute_calls, path, birthday, as_of
):
    client.post(
        path,
        json={
            "birthday": birthday,
            "as_of": as_of,
            "categories": ["stars", "links", "stars"],
            "star_limit": 7,
        },
    )
    assert compute_calls == [
        (date(1998, 11, 15), date(2026, 4, 11), {"stars", "links"}, 7)
    ]


@pytest.mark.parametrize(
    ("path", "birthday"),
    [(BIG, "1998-11-15"), (MIDDLE, "11/15/1998"), (LITTLE, "15/11/1998")],
    ids=["big-endian", "middle-endian", "little-endian"],
)
def test_left_out_categories_and_star_limit_mean_all_and_500(
    client, compute_calls, path, birthday
):
    client.post(path, json={"birthday": birthday})
    [(_, _, categories, star_limit)] = compute_calls
    assert (categories, star_limit) == (EVERY_CATEGORY, 500)


class BlockingCompute:
    """Stands in for compute_first_light; each call blocks until released.

    ``events`` lists each call's ("start", birth) and ("finish", birth)
    in the order they happened.
    """

    def __init__(self):
        self.events = []
        self._started = queue.Queue()
        self._releases = {
            date.fromisoformat(day): threading.Event()
            for day in CONCURRENT_BIRTHDAYS
        }

    def __call__(self, birth, as_of, categories, star_limit):
        self.events.append(("start", birth))
        self._started.put(birth)
        self._releases[birth].wait(WAIT_LIMIT_SECONDS)
        self.events.append(("finish", birth))
        return FirstLightResponse(
            birthday=birth.isoformat(), as_of=as_of.isoformat()
        )

    def next_start(self, timeout):
        """Gives the birthday of the next call to start, or None."""
        try:
            return self._started.get(timeout=timeout)
        except queue.Empty:
            return None

    def release(self, birth):
        self._releases[birth].set()

    def release_all(self):
        for release in self._releases.values():
            release.set()


def test_third_computation_waits_until_one_of_two_finishes(monkeypatch):
    compute = BlockingCompute()
    monkeypatch.setattr(routes, "compute_first_light", compute)

    async def ask_three_at_once():
        asked = [
            asyncio.create_task(
                routes.big_endian_first_light(
                    BigEndianRequest(birthday=day, as_of="2026-11-18")
                )
            )
            for day in CONCURRENT_BIRTHDAYS
        ]
        try:
            first = await asyncio.to_thread(
                compute.next_start, WAIT_LIMIT_SECONDS
            )
            await asyncio.to_thread(compute.next_start, WAIT_LIMIT_SECONDS)
            await asyncio.sleep(SETTLE_SECONDS)
            compute.release(first)
            await asyncio.to_thread(compute.next_start, WAIT_LIMIT_SECONDS)
        finally:
            compute.release_all()
        await asyncio.gather(*asked)

    asyncio.run(ask_three_at_once())

    assert [kind for kind, _ in compute.events] == [
        "start",
        "start",
        "finish",
        "start",
        "finish",
        "finish",
    ]


@pytest.mark.parametrize(
    ("endpoint", "request_model", "birthday_text", "as_of_text"),
    [
        (
            routes.big_endian_first_light,
            BigEndianRequest,
            "1998-11-15",
            "2026-11-18",
        ),
        (
            routes.middle_endian_first_light,
            MiddleEndianRequest,
            "11/15/1998",
            "11/18/2026",
        ),
        (
            routes.little_endian_first_light,
            LittleEndianRequest,
            "15/11/1998",
            "18/11/2026",
        ),
    ],
    ids=["big-endian", "middle-endian", "little-endian"],
)
def test_computation_runs_off_the_event_loop_thread(
    monkeypatch, endpoint, request_model, birthday_text, as_of_text
):
    compute_threads = []

    def record_thread(birth, as_of, categories, star_limit):
        compute_threads.append(threading.get_ident())
        return FirstLightResponse(
            birthday=birth.isoformat(), as_of=as_of.isoformat()
        )

    monkeypatch.setattr(routes, "compute_first_light", record_thread)

    async def ask():
        await endpoint(request_model(birthday=birthday_text, as_of=as_of_text))
        return threading.get_ident()

    loop_thread = asyncio.run(ask())

    [compute_thread] = compute_threads
    assert compute_thread != loop_thread


def frozen_datetime(utc_now, local_offset):
    """A datetime class whose clock stands still at ``utc_now``.

    Without a time zone, ``now`` gives the local time of a server
    ``local_offset`` away from UTC.
    """

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return (utc_now + local_offset).replace(tzinfo=None)
            return utc_now.astimezone(tz)

    return Frozen


@pytest.mark.parametrize(
    ("as_of", "utc_now", "local_offset", "expected"),
    [
        (
            {},
            datetime(2026, 3, 31, 23, 30, tzinfo=UTC),
            timedelta(hours=14),
            "2026-03-31",
        ),
        (
            {},
            datetime(2026, 4, 1, 0, 30, tzinfo=UTC),
            timedelta(hours=-10),
            "2026-04-01",
        ),
        (
            {"as_of": None},
            datetime(2026, 3, 31, 23, 30, tzinfo=UTC),
            timedelta(hours=14),
            "2026-03-31",
        ),
    ],
    ids=["local-day-ahead", "local-day-behind", "as-of-null"],
)
def test_default_as_of_is_the_utc_date(
    client, monkeypatch, as_of, utc_now, local_offset, expected
):
    monkeypatch.setattr(
        routes, "datetime", frozen_datetime(utc_now, local_offset)
    )
    response = client.post(
        BIG, json={"birthday": "2026-03-01", "categories": ["links"], **as_of}
    )
    assert response.json()["as_of"] == expected


@pytest.mark.parametrize(
    ("path", "payload", "detail"),
    [
        (BIG, {"birthday": "bad"}, "Invalid date: 'bad'. Expected YYYY-MM-DD."),
        (
            BIG,
            {"birthday": "1998-02-30"},
            "Invalid date: '1998-02-30'. Expected YYYY-MM-DD.",
        ),
        (
            BIG,
            {"birthday": "1998-11-15", "as_of": "15/11/2026"},
            "Invalid date: '15/11/2026'. Expected YYYY-MM-DD.",
        ),
        (
            BIG,
            {"birthday": "1998-11-15", "as_of": ""},
            "Invalid date: ''. Expected YYYY-MM-DD.",
        ),
        (
            BIG,
            {"birthday": "bad", "as_of": "worse"},
            "Invalid date: 'bad'. Expected YYYY-MM-DD.",
        ),
        (
            MIDDLE,
            {"birthday": "1998-11-15"},
            "Invalid date: '1998-11-15'. Expected MM/DD/YYYY.",
        ),
        (
            MIDDLE,
            {"birthday": "11/15/1998", "as_of": "18/11/2026"},
            "Invalid date: '18/11/2026'. Expected MM/DD/YYYY.",
        ),
        (
            LITTLE,
            {"birthday": "11/15/1998"},
            "Invalid date: '11/15/1998'. Expected DD/MM/YYYY.",
        ),
        (
            LITTLE,
            {"birthday": "15/11/1998", "as_of": "2026-11-18"},
            "Invalid date: '2026-11-18'. Expected DD/MM/YYYY.",
        ),
    ],
    ids=[
        "big-endian-not-a-date",
        "big-endian-30-february",
        "big-endian-as-of-in-another-format",
        "big-endian-empty-as-of",
        "birthday-reported-before-as-of",
        "middle-endian-given-big-endian",
        "middle-endian-as-of-in-another-format",
        "little-endian-given-middle-endian",
        "little-endian-as-of-in-another-format",
    ],
)
def test_date_that_does_not_parse_is_a_422(client, path, payload, detail):
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    "birthday", ["2030-01-01", "2026-11-18"], ids=["after-as-of", "on-as-of"]
)
def test_birthday_not_before_as_of_is_a_422(client, birthday):
    response = client.post(
        BIG, json={"birthday": birthday, "as_of": "2026-11-18"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Birthday must be in the past."}


def test_birthday_the_day_before_as_of_is_accepted(client):
    response = client.post(
        BIG,
        json={
            "birthday": "2026-11-17",
            "as_of": "2026-11-18",
            "categories": ["links"],
        },
    )
    assert response.status_code == 200
