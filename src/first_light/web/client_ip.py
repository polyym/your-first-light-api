"""Works out which caller a request came from, for rate limits and logs.

Two environment variables adapt this to a deployment:

- ``CLIENT_IP_HEADER`` names a header that the platform's edge sets to
  the verified caller address. On Render it defaults to
  ``True-Client-IP``.
- ``TRUSTED_PROXY_HOPS`` is the number of reverse proxies in front of
  the app, for a conventional proxy chain with no such header.

With neither, the peer address the server reports is used: on a port
exposed directly, forwarding headers are whatever the caller wants them
to be.
"""

import os

from fastapi import Request

from first_light.constants import RENDER_CLIENT_IP_HEADER, RENDER_ENV_VAR


def _client_ip_header() -> str:
    # A Render service created outside a blueprint never receives the
    # variables in render.yaml, so its default cannot depend on them.
    configured = os.environ.get("CLIENT_IP_HEADER", "").strip()
    if configured:
        return configured
    if os.environ.get(RENDER_ENV_VAR):
        return RENDER_CLIENT_IP_HEADER
    return ""


def _trusted_proxy_hops() -> int:
    # A blank value counts as unset, as it does for the header. Anything
    # else that is not a whole number stops the app at start-up, before
    # it can limit every caller as one.
    return int(os.environ.get("TRUSTED_PROXY_HOPS", "").strip() or "0")


CLIENT_IP_HEADER = _client_ip_header()
TRUSTED_PROXY_HOPS = _trusted_proxy_hops()


def client_ip(request: Request) -> str:
    """Gives the caller's address, or ``"unknown"`` when there is none.

    A platform header wins over the hop count, because a platform's own
    chain can hold a varying number of proxies, as Render's does.
    """
    if CLIENT_IP_HEADER:
        # The header holds one address; the split is defensive.
        value = request.headers.get(CLIENT_IP_HEADER, "")
        address = value.split(",")[0].strip()
        if address:
            return address
    if TRUSTED_PROXY_HOPS > 0:
        # A proxy may add its own header line rather than extend the
        # first; the lines together form one list.
        forwarded = ",".join(request.headers.getlist("x-forwarded-for"))
        if forwarded:
            entries = [e.strip() for e in forwarded.split(",") if e.strip()]
            # Each trusted proxy appends the peer it accepted, so the
            # caller is the hops-th entry from the right. Anything further
            # left came from the caller and is never trusted.
            if len(entries) >= TRUSTED_PROXY_HOPS:
                return entries[-TRUSTED_PROXY_HOPS]
            if entries:
                # A shorter chain than configured: some proxies were
                # bypassed, so take the outermost entry.
                return entries[0]
    if request.client:
        return request.client.host
    return "unknown"
