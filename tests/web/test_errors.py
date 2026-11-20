"""Tests for the 422 and 500 handlers and the shape of error bodies."""

import asyncio
import json
import logging

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.requests import Request

from first_light.app import app
from first_light.constants import MAX_BODY_BYTES
from first_light.web import routes
from first_light.web.errors import handle_validation_error

BIG = "/v1/big-endian-first-light"
MIDDLE = "/v1/middle-endian-first-light"
LITTLE = "/v1/little-endian-first-light"
JSON = "application/json"
UNKNOWN_CATEGORY = (
    "categories.1: Input should be 'time_alive', 'moon', 'light_sphere', "
    "'stars', 'exoplanets', 'star_classification', 'planetary_ages', "
    "'body_stats', 'cosmic_journey', 'scale_comparisons', "
    "'universe_perspective', 'voyagers', 'eclipses', 'links' or "
    "'sun_constellation'"
)
VALID = {
    "birthday": "1998-11-15",
    "as_of": "2026-11-18",
    "categories": ["links"],
}


def encode(payload):
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    ("body", "content_type", "detail"),
    [
        (b"{nope", JSON, "Request body is not valid JSON."),
        (b"", JSON, "Request body is required."),
        (b"null", JSON, "Request body must be a JSON object."),
        (b"[]", JSON, "Request body must be a JSON object."),
        (b'"1998-11-15"', JSON, "Request body must be a JSON object."),
        (
            b"[]",
            "application/vnd.api+json",
            "Request body must be a JSON object.",
        ),
        (
            b"[]",
            "Application/JSON; charset=utf-8",
            "Request body must be a JSON object.",
        ),
        (encode(VALID), "text/plain", "Content-Type must be application/json."),
        (
            encode(VALID),
            "application/x-www-form-urlencoded",
            "Content-Type must be application/json.",
        ),
        (encode(VALID), None, "Content-Type must be application/json."),
        (b"", "text/plain", "Request body is required."),
        (encode({"as_of": "2026-11-18"}), JSON, "birthday: Field required"),
        (
            encode({"birthday": "1998-11-15", "categories": ["links", "nope"]}),
            JSON,
            UNKNOWN_CATEGORY,
        ),
        (
            encode({"star_limit": 0, "categories": []}),
            JSON,
            "categories: List should have at least 1 item after validation, "
            "not 0",
        ),
        (
            encode({"birthday": 19981115}),
            JSON,
            "birthday: Input should be a valid string",
        ),
        (
            encode({"birthday": "1998-11-15", "categories": ["links"] * 16}),
            JSON,
            "categories: List should have at most 15 items after validation, "
            "not 16",
        ),
        (
            encode({"birthday": "1998-11-15", "star_limit": 0}),
            JSON,
            "star_limit: Input should be greater than or equal to 1",
        ),
        (
            encode({"birthday": "1998-11-15", "star_limit": 50_001}),
            JSON,
            "star_limit: Input should be less than or equal to 50000",
        ),
        (
            encode({"birthday": "1998-11-15", "star_limit": "ten"}),
            JSON,
            "star_limit: Input should be a valid integer, unable to parse "
            "string as an integer",
        ),
        (
            encode({"birthday": "1998-11-15", "star_limit": 5.5}),
            JSON,
            "star_limit: Input should be a valid integer, got a number with "
            "a fractional part",
        ),
    ],
    ids=[
        "bad-json",
        "empty-body",
        "json-null",
        "array",
        "string",
        "array-as-plus-json",
        "array-as-json-with-parameters",
        "text-plain",
        "form",
        "no-content-type",
        "empty-body-as-text-plain",
        "missing-field",
        "list-index",
        "first-of-several-errors",
        "birthday-number",
        "sixteen-categories",
        "star-limit-below-1",
        "star-limit-over-50000",
        "star-limit-text",
        "star-limit-fraction",
    ],
)
def test_invalid_request_gets_one_plain_sentence(
    client, body, content_type, detail
):
    headers = {"Content-Type": content_type} if content_type else {}
    response = client.post(BIG, content=body, headers=headers)
    assert response.status_code == 422
    assert response.json() == {"detail": detail}


# The details clients get, on every endpoint.
@pytest.mark.parametrize(
    ("path", "payload", "detail"),
    [
        (
            BIG,
            {"birthday": "1998-11-15x"},
            "birthday: String should have at most 10 characters",
        ),
        (
            BIG,
            {"birthday": "1998-11-15", "as_of": "2026-11-18x"},
            "as_of: String should have at most 10 characters",
        ),
        (
            MIDDLE,
            {"birthday": "11/15/1998x"},
            "birthday: String should have at most 10 characters",
        ),
        (
            MIDDLE,
            {"birthday": "11/15/1998", "as_of": "11/18/2026x"},
            "as_of: String should have at most 10 characters",
        ),
        (
            LITTLE,
            {"birthday": "15/11/1998x"},
            "birthday: String should have at most 10 characters",
        ),
        (
            LITTLE,
            {"birthday": "15/11/1998", "as_of": "18/11/2026x"},
            "as_of: String should have at most 10 characters",
        ),
    ],
    ids=[
        "big-endian-birthday",
        "big-endian-as-of",
        "middle-endian-birthday",
        "middle-endian-as-of",
        "little-endian-birthday",
        "little-endian-as-of",
    ],
)
def test_over_long_date_is_refused_before_it_is_parsed(
    client, path, payload, detail
):
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    "changes",
    [
        {"star_limit": 1},
        {"star_limit": 50_000},
        {"categories": ["links"] * 15},
    ],
    ids=["star-limit-1", "star-limit-50000", "fifteen-categories"],
)
def test_values_at_the_limits_are_accepted(client, changes):
    assert client.post(BIG, json={**VALID, **changes}).status_code == 200


def test_422_carries_cors(client):
    response = client.post(
        BIG,
        content=b"{nope",
        headers={"Content-Type": JSON, "Origin": "https://example.org"},
    )
    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] == "*"


def test_body_that_is_not_utf8_is_a_400(client):
    response = client.post(
        BIG,
        content=b'{"birthday": "\xff\xfe"}',
        headers={"Content-Type": JSON},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "There was an error parsing the body"}


@pytest.mark.parametrize(
    ("errors", "detail"),
    [
        ([], "Invalid request."),
        (
            [{"type": "value_error", "loc": ("body",), "msg": "Value error"}],
            "Value error",
        ),
        (
            [
                {
                    "type": "missing",
                    "loc": ("query", "q"),
                    "msg": "Field required",
                }
            ],
            "query.q: Field required",
        ),
        (
            [{"type": "string_type", "loc": ("body", "a")}],
            "a: Invalid request.",
        ),
        ([{"type": "value_error", "msg": "Value error"}], "Value error"),
        (
            [
                {
                    "type": "dict_type",
                    "loc": ("body",),
                    "msg": "Input should be a valid dictionary",
                }
            ],
            "Content-Type must be application/json.",
        ),
    ],
    ids=[
        "no-errors",
        "body-level-message",
        "outside-the-body",
        "no-message",
        "no-location",
        "dictionary-body-not-declared-json",
    ],
)
def test_validation_error_detail_falls_back_sensibly(errors, detail):
    request = Request({"type": "http", "method": "POST", "headers": []})
    response = asyncio.run(
        handle_validation_error(request, RequestValidationError(errors))
    )
    assert response.status_code == 422
    assert json.loads(response.body) == {"detail": detail}


@pytest.fixture
def failing_client(monkeypatch):
    """A client whose POST endpoints raise an unexpected error."""

    def broken(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "compute_first_light", broken)
    return TestClient(app, raise_server_exceptions=False)


def test_documented_error_examples_are_the_details_clients_get(
    failing_client,
):
    schema = failing_client.get("/openapi.json").json()
    documented = schema["paths"][BIG]["post"]["responses"]
    answers = {
        "400": failing_client.post(
            BIG, content=b'{"birthday": "\xff"}', headers={"Content-Type": JSON}
        ),
        "413": failing_client.post(
            BIG,
            content=b"x" * (MAX_BODY_BYTES + 1),
            headers={"Content-Type": JSON},
        ),
        "500": failing_client.post(BIG, json=VALID),
    }

    for status, answer in answers.items():
        example = documented[status]["content"][JSON]["example"]
        assert (answer.status_code, answer.json()) == (int(status), example)


@pytest.mark.parametrize(
    ("path", "birthday"),
    [(BIG, "2999-01-01"), (MIDDLE, "01/01/2999"), (LITTLE, "01/01/2999")],
)
def test_documented_422_example_is_a_detail_every_endpoint_gives(
    client, path, birthday
):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    (example,) = schemas["ErrorResponse"]["properties"]["detail"]["examples"]

    response = client.post(path, json={"birthday": birthday})

    assert (response.status_code, response.json()) == (
        422,
        {"detail": example},
    )


def test_unexpected_error_is_a_plain_500(failing_client):
    response = failing_client.post(BIG, json=VALID)
    assert response.status_code == 500
    assert response.json() == {"detail": "An unexpected error occurred."}


@pytest.mark.parametrize(
    ("headers", "allow_origin"),
    [({"Origin": "https://example.org"}, "*"), ({}, None)],
    ids=["cross-origin", "same-origin"],
)
def test_500_carries_cors_only_for_a_cross_origin_request(
    failing_client, headers, allow_origin
):
    response = failing_client.post(BIG, json=VALID, headers=headers)
    assert response.headers.get("access-control-allow-origin") == allow_origin


@pytest.mark.parametrize(
    "headers",
    [{"Origin": "https://example.org"}, {}],
    ids=["cross-origin", "same-origin"],
)
def test_500_names_origin_in_vary_as_the_cors_middleware_does(
    failing_client, headers
):
    """The 500 handler runs outside that middleware and copies it."""
    through_cors = failing_client.post(BIG, json={}, headers=headers)
    failed = failing_client.post(BIG, json=VALID, headers=headers)

    assert (through_cors.status_code, failed.status_code) == (422, 500)
    assert through_cors.headers["vary"] == failed.headers["vary"] == "Origin"


def test_500_handler_leaves_the_traceback_to_the_server(failing_client, caplog):
    with caplog.at_level(logging.DEBUG):
        failing_client.post(BIG, json=VALID)
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
