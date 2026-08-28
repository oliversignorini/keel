"""Sentry wiring (PRD §4 Integration points: "Both runtimes, releases
tied to git SHA, source maps uploaded").

No DSN exists for this project yet. ``sentry_sdk.init()`` with a blank
``dsn`` makes the SDK a documented no-op — every call in this module is
always safe to make, wired or not — so this is unconditional in
``config/settings/base.py`` rather than gated behind ``if
settings.SENTRY_DSN``. What's provable without real credentials is the
event *shape*: ``keel/core/tests/test_sentry.py`` swaps in a stub
``Transport`` and asserts the captured envelope's release, tags and
exception against it — the honest substitute for "a deliberate error
appears in Sentry with the correct release and readable stack" until a
real DSN exists.
"""

from typing import Any, Literal

import sentry_sdk
from django.conf import settings
from sentry_sdk.integrations.logging import LoggingIntegration

from keel.core.redaction import redact_mapping

_LogLevel = Literal["fatal", "critical", "error", "warning", "info", "debug"]

# The event sections that can carry secret-shaped values: request headers/
# cookies/body, and any breadcrumb/extra data a call site attached.
# `send_default_pii=False` below already keeps Sentry from *collecting*
# cookies/IPs itself, but a call site can still put a secret into `extra`
# or a breadcrumb explicitly (e.g. logging a webhook payload for
# debugging) — this is the layer below `send_default_pii` that catches
# that.
_SCRUBBED_EVENT_KEYS = ("extra", "contexts", "breadcrumbs")


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """``before_send`` — redacts secret-shaped keys anywhere in the parts
    of a Sentry event a call site controls, using the same denylist
    ``keel.core.logging.JSONFormatter`` scrubs log lines with
    (``keel.core.redaction``), so "what counts as a secret" can't drift
    between the two. Never drops the event — only redacts values."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("headers", "cookies", "data"):
            if key in request:
                request[key] = redact_mapping(request[key])

    for key in _SCRUBBED_EVENT_KEYS:
        if key in event:
            event[key] = redact_mapping(event[key])

    return event


def init_sentry(**overrides: Any) -> None:
    """Called once from ``keel.core.apps.CoreConfig.ready()``.
    ``overrides`` lets tests swap in a stub ``transport`` (and override
    ``release``/``environment``) without duplicating every other
    argument."""
    options: dict[str, Any] = {
        "dsn": settings.SENTRY_DSN or None,
        "environment": settings.SENTRY_ENVIRONMENT,
        "release": settings.SENTRY_RELEASE,
        # PII (request bodies, cookies, user IPs by default) — off until
        # a project has decided it needs that in Sentry, not a template
        # default. Sentry's own `send_default_pii` guidance is the same.
        "send_default_pii": False,
        "traces_sample_rate": 0.0,
        # event_level=None: an ERROR-level log call (e.g. the dead-letter
        # path's logger.error()) becomes a breadcrumb only, never a
        # second event alongside the explicit capture_exception() call
        # keel.core.sentry.report_exception already makes for the same
        # failure — Sentry's default (event_level=ERROR) would otherwise
        # double every dead-lettered task into two events.
        "integrations": [LoggingIntegration(level=20, event_level=None)],
        # The redaction layer below send_default_pii — see scrub_event's
        # docstring.
        "before_send": scrub_event,
    }
    options.update(overrides)
    sentry_sdk.init(**options)


def report_exception(exc: BaseException, *, tags: dict[str, str] | None = None) -> None:
    """Every dead-letter path's Sentry seam (``keel.core.tasks``,
    ``keel.billing.tasks``) calls this rather than ``sentry_sdk.capture_
    exception`` directly, so both go through one place that can add
    tags without duplicating the ``new_scope()`` dance at each call site."""
    with sentry_sdk.new_scope() as scope:
        for key, value in (tags or {}).items():
            scope.set_tag(key, value)
        sentry_sdk.capture_exception(exc)


def report_message(
    message: str, *, level: _LogLevel = "warning", tags: dict[str, str] | None = None
) -> None:
    """The non-exception counterpart to ``report_exception`` — for a
    condition worth an alert with no exception to attach (ddia#4: a
    ``check_credit_balances_task`` drift finding is a fact about state,
    not a stack trace)."""
    with sentry_sdk.new_scope() as scope:
        for key, value in (tags or {}).items():
            scope.set_tag(key, value)
        sentry_sdk.capture_message(message, level=level)
