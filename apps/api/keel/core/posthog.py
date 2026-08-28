"""PostHog — server-side capture (PRD §4 Integration points: "Client-
side, with a server-side capture helper for billing events").

No project key exists for this project yet. ``posthog.Posthog(...,
disabled=True)`` is a documented no-op — every event is dropped rather
than queued or sent — so ``capture_billing_event`` is always safe to
call. What's provable without a real key is the call *shape*:
``keel/core/tests/test_posthog.py`` patches the client's ``capture``
method and asserts the event name, distinct id and properties it was
called with.
"""

from typing import Any

from django.conf import settings
from posthog import Posthog

_client: Posthog | None = None


def get_client() -> Posthog:
    """Lazy singleton — built on first use rather than at import time, so
    tests can patch ``settings.POSTHOG_PROJECT_API_KEY`` before anything
    constructs a client against the old value."""
    global _client
    if _client is None:
        _client = Posthog(
            project_api_key=settings.POSTHOG_PROJECT_API_KEY or "phc_disabled",
            host=settings.POSTHOG_HOST,
            disabled=not settings.POSTHOG_PROJECT_API_KEY,
        )
    return _client


def reset_client() -> None:
    """Test-only: forces the next ``get_client()`` to rebuild against
    current settings, and to reset the mock/patched client above."""
    global _client
    _client = None


def capture_billing_event(
    *, distinct_id: str, event: str, properties: dict[str, Any] | None = None
) -> None:
    """The one call point every billing webhook handler goes through
    (``keel.billing.webhooks``) — a project.captures billing events
    (subscription started/updated/canceled, invoice paid/failed) this
    way rather than calling ``posthog.capture`` directly, so there is one
    place to add default properties or swap capture strategies later."""
    get_client().capture(distinct_id=distinct_id, event=event, properties=properties or {})
