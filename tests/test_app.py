"""Tests for how the assembled app compresses its responses."""

BIG = "/v1/big-endian-first-light"
ACCEPTS_GZIP = {"Accept-Encoding": "gzip"}
# The 7,831-byte answer to the first of these is over GZIP_MINIMUM_BYTES;
# the 664-byte answer to the second is under it.
TWENTY_FIVE_STARS = {
    "birthday": "1988-03-21",
    "as_of": "2026-11-18",
    "categories": ["stars"],
    "star_limit": 25,
}
PLANETARY_AGES = {
    "birthday": "1988-03-21",
    "as_of": "2026-11-18",
    "categories": ["planetary_ages"],
}


def test_large_response_is_gzipped(client):
    response = client.post(BIG, json=TWENTY_FIVE_STARS, headers=ACCEPTS_GZIP)

    assert response.headers.get("content-encoding") == "gzip"


def test_small_response_is_sent_uncompressed(client):
    response = client.post(BIG, json=PLANETARY_AGES, headers=ACCEPTS_GZIP)

    assert "content-encoding" not in response.headers
