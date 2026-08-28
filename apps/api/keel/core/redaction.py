"""The one place secret-shaped values get scrubbed before they leave the
process — redaction of auth headers, cookies, CSRF and session IDs,
OAuth tokens, API keys, Stripe secrets, passwords and sensitive request
fields. ``keel.core.logging.JSONFormatter``
and ``keel.core.sentry``'s ``before_send`` scrubber both call
``redact_mapping`` rather than each maintaining their own denylist, so the
vocabulary of "what counts as a secret" can't drift between the two
places a request can leak one.

Matching is substring, case-insensitive, against the *key* — not a
regex over values — because a value is opaque (an access token has no
distinguishing shape a password doesn't also have) but a key almost
always names what it holds. This is deliberately over-inclusive: a false
positive redacts a field that wasn't actually sensitive, which costs a
developer a moment of "why is this scrubbed"; a false negative leaks a
real secret into a log aggregator or Sentry project, which is the
failure mode this module exists to prevent. When those two costs
disagree, over-redact.
"""

from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

# Substrings, not exact names — "csrftoken", "x-csrftoken", and "csrf_token"
# all match "csrf", "sessionid" and "session_key" both match "session", etc.
# Deliberately broad per the module docstring's over-redact rule.
_SENSITIVE_KEY_SUBSTRINGS = (
    "authorization",
    "cookie",
    "csrf",
    "session",
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "signature",  # Stripe-Signature and similar webhook secrets
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(marker in lowered for marker in _SENSITIVE_KEY_SUBSTRINGS)


def redact_mapping(data: Any) -> Any:
    """Recursively walks ``data`` (dicts, lists/tuples, and scalars) and
    replaces the value of any dict key matching ``is_sensitive_key`` with
    ``REDACTED``. Returns a new structure — never mutates ``data`` in
    place, since a caller (e.g. Sentry's ``before_send``) may not expect
    its argument to change under it."""
    if isinstance(data, Mapping):
        return {
            key: REDACTED if is_sensitive_key(str(key)) else redact_mapping(value)
            for key, value in data.items()
        }
    if isinstance(data, str | bytes):
        return data
    if isinstance(data, Sequence):
        return [redact_mapping(item) for item in data]
    return data
