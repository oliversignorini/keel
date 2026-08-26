"""Sentry wiring (PRD §4 Integration points: "Both runtimes, releases
tied to git SHA, source maps uploaded"; docs/plans/phase-8.md 8.4).

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

from typing import Any

import sentry_sdk
from django.conf import settings
from sentry_sdk.integrations.logging import LoggingIntegration


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
