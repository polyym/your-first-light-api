"""Names, limits and timings of the HTTP service.

Physical and astronomical values live in ``facts.physics``.
"""

API_TITLE = "Your First Light"
API_DESCRIPTION = "Post your birthday. Discover your cosmic reach."
# Must equal the version in pyproject.toml; a test holds them together.
API_VERSION = "1.1.0"

# A valid request is a few hundred bytes. Without a cap, a body is read
# into memory in full before validation, at the cost to the caller of
# a rate-limit slot that the resulting 422 refunds.
MAX_BODY_BYTES = 64 * 1024

# Clients parse the wait out of the 429 and retry once, waiting at most
# 60 seconds, so the window must not grow past that.
RATE_LIMIT_SECONDS = 30
# An IPv6 subscriber is given a whole /64 network.
IPV6_CALLER_PREFIX = 64

# Responses smaller than this are not worth compressing.
GZIP_MINIMUM_BYTES = 1000

STAR_LIMIT_DEFAULT = 500
STAR_LIMIT_MAX = 50_000
# At most this many first-light requests are computed and encoded at
# once. A response of STAR_LIMIT_MAX stars holds about 100 MB until it
# is ready, and Render's free instance has 512 MB. The server keeps a
# body its caller has yet to read, 16 MB uncompressed, outside this limit.
MAX_CONCURRENT_COMPUTATIONS = 2

# YYYY-MM-DD, MM/DD/YYYY and DD/MM/YYYY are all ten characters.
DATE_TEXT_MAX_LENGTH = 10

# Render fronts every service with Cloudflare, which sets this header
# to the verified caller address. Render sets RENDER on every service.
RENDER_ENV_VAR = "RENDER"
RENDER_CLIENT_IP_HEADER = "True-Client-IP"
