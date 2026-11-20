"""Tests for working out which caller a request came from."""

import importlib

import pytest
from starlette.requests import Request

from first_light.web import client_ip
from first_light.web.client_ip import _client_ip_header, _trusted_proxy_hops

PEER = "192.0.2.1"
BIG = "/v1/big-endian-first-light"
REQUEST = {
    "birthday": "1998-11-15",
    "as_of": "2026-11-18",
    "categories": ["links"],
}
ENVIRONMENT_VARIABLES = ("CLIENT_IP_HEADER", "TRUSTED_PROXY_HOPS", "RENDER")


def make_request(headers=(), client=(PEER, 50000)):
    """Builds a request with the given header lines and peer."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in headers
            ],
            "client": client,
        }
    )


@pytest.fixture
def configure(monkeypatch):
    """Sets the platform header and the trusted hop count."""

    def apply(header="", hops=0):
        monkeypatch.setattr(client_ip, "CLIENT_IP_HEADER", header)
        monkeypatch.setattr(client_ip, "TRUSTED_PROXY_HOPS", hops)

    apply()
    return apply


@pytest.fixture
def unconfigured(monkeypatch):
    """Reloads client_ip with none of its environment variables set.

    Every name the reload rebinds is restored afterwards, so the rest of
    the suite sees the module as it was.
    """
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in list(vars(client_ip).items()):
        if not name.startswith("__"):
            monkeypatch.setattr(client_ip, name, value)
    importlib.reload(client_ip)


@pytest.mark.usefixtures("unconfigured")
def test_unconfigured_app_does_not_let_x_forwarded_for_dodge_the_limit(
    client,
):
    first = client.post(
        BIG, json=REQUEST, headers={"X-Forwarded-For": "198.51.100.1"}
    )
    second = client.post(
        BIG, json=REQUEST, headers={"X-Forwarded-For": "198.51.100.2"}
    )
    assert (first.status_code, second.status_code) == (200, 429)


def test_forwarding_headers_are_ignored_without_configuration(configure):
    request = make_request(
        [
            ("True-Client-IP", "203.0.113.5"),
            ("X-Forwarded-For", "198.51.100.7"),
        ]
    )
    assert client_ip.client_ip(request) == PEER


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("203.0.113.5", "203.0.113.5"),
        ("203.0.113.5, 10.0.0.1", "203.0.113.5"),
        ("  203.0.113.5  ,10.0.0.1", "203.0.113.5"),
        ("2001:db8::5", "2001:db8::5"),
    ],
    ids=["single", "comma-list", "padded", "ipv6"],
)
def test_platform_header_gives_its_first_address(configure, value, expected):
    configure(header="True-Client-IP")
    request = make_request([("True-Client-IP", value)])
    assert client_ip.client_ip(request) == expected


def test_platform_header_wins_over_the_hop_count(configure):
    configure(header="True-Client-IP", hops=1)
    request = make_request(
        [
            ("True-Client-IP", "203.0.113.5"),
            ("X-Forwarded-For", "198.51.100.7"),
        ]
    )
    assert client_ip.client_ip(request) == "203.0.113.5"


@pytest.mark.parametrize(
    "headers",
    [
        [("X-Forwarded-For", "198.51.100.7")],
        [("True-Client-IP", ""), ("X-Forwarded-For", "198.51.100.7")],
        [("True-Client-IP", " , "), ("X-Forwarded-For", "198.51.100.7")],
    ],
    ids=["header-absent", "header-empty", "header-without-an-address"],
)
def test_missing_platform_header_falls_back_to_the_hop_count(
    configure, headers
):
    configure(header="True-Client-IP", hops=1)
    assert client_ip.client_ip(make_request(headers)) == "198.51.100.7"


@pytest.mark.parametrize(
    ("hops", "forwarded", "expected"),
    [
        (1, "198.51.100.7", "198.51.100.7"),
        (1, "203.0.113.66, 198.51.100.7", "198.51.100.7"),
        (2, "198.51.100.7, 10.0.0.2", "198.51.100.7"),
        (2, "203.0.113.66, 198.51.100.7, 10.0.0.2", "198.51.100.7"),
        (3, "198.51.100.7, 10.0.0.2", "198.51.100.7"),
        (2, "198.51.100.7, , 10.0.0.2", "198.51.100.7"),
    ],
    ids=[
        "one-hop",
        "one-hop-spoofed-entry-ignored",
        "two-hops-exact-chain",
        "two-hops-longer-chain",
        "three-hops-shorter-chain-takes-leftmost",
        "empty-entries-skipped",
    ],
)
def test_hop_count_picks_the_entry_the_first_trusted_proxy_added(
    configure, hops, forwarded, expected
):
    configure(hops=hops)
    request = make_request([("X-Forwarded-For", forwarded)])
    assert client_ip.client_ip(request) == expected


def test_several_forwarded_lines_are_read_as_one_list(configure):
    configure(hops=2)
    request = make_request(
        [
            ("X-Forwarded-For", "203.0.113.66, 198.51.100.7"),
            ("X-Forwarded-For", "10.0.0.2"),
        ]
    )
    assert client_ip.client_ip(request) == "198.51.100.7"


@pytest.mark.parametrize(
    "headers",
    [[], [("X-Forwarded-For", " , ")]],
    ids=["no-forwarded-header", "forwarded-header-without-entries"],
)
def test_hop_count_without_entries_falls_back_to_the_peer(configure, headers):
    configure(hops=1)
    assert client_ip.client_ip(make_request(headers)) == PEER


def test_negative_hop_count_trusts_no_forwarded_entry(configure):
    configure(hops=-1)
    request = make_request([("X-Forwarded-For", "203.0.113.66, 198.51.100.7")])
    assert client_ip.client_ip(request) == PEER


@pytest.mark.parametrize(
    "hops", [0, 1], ids=["no-hops", "hops-without-forwarded-header"]
)
def test_request_without_a_peer_is_unknown(configure, hops):
    configure(hops=hops)
    assert client_ip.client_ip(make_request(client=None)) == "unknown"


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, ""),
        ({"CLIENT_IP_HEADER": "Fly-Client-IP"}, "Fly-Client-IP"),
        ({"CLIENT_IP_HEADER": "  CF-Connecting-IP  "}, "CF-Connecting-IP"),
        ({"RENDER": "true"}, "True-Client-IP"),
        (
            {"RENDER": "true", "CLIENT_IP_HEADER": "Fly-Client-IP"},
            "Fly-Client-IP",
        ),
        ({"RENDER": "true", "CLIENT_IP_HEADER": "   "}, "True-Client-IP"),
        ({"RENDER": ""}, ""),
    ],
    ids=[
        "neither",
        "configured",
        "configured-padded",
        "render-default",
        "configured-wins-on-render",
        "blank-configured-on-render",
        "render-empty",
    ],
)
def test_platform_header_name_comes_from_the_environment(
    monkeypatch, environment, expected
):
    monkeypatch.delenv("CLIENT_IP_HEADER", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert _client_ip_header() == expected


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, 0),
        ({"TRUSTED_PROXY_HOPS": "2"}, 2),
        ({"TRUSTED_PROXY_HOPS": " 2 "}, 2),
        ({"TRUSTED_PROXY_HOPS": ""}, 0),
        ({"TRUSTED_PROXY_HOPS": "   "}, 0),
    ],
    ids=["unset", "set", "padded", "empty", "blank"],
)
def test_hop_count_comes_from_the_environment(
    monkeypatch, environment, expected
):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert _trusted_proxy_hops() == expected


def test_hop_count_that_is_not_a_whole_number_stops_the_app(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "two")
    with pytest.raises(ValueError):
        _trusted_proxy_hops()
