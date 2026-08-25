"""Sentry wiring (PRD §4 Integration points; docs/plans/phase-8.md 8.4).

No DSN exists for this project (assert against a stub transport, see
module docstring below), so what these tests actually prove is the
*shape* — release, tags, exception type and message reach a captured
event exactly as ``keel.core.sentry.report_exception`` and the dead-
letter call sites (``keel.core.tasks``, ``keel.billing.tasks``) send
them. Which criteria need a real DSN: seeing the event actually land in
a Sentry project, and source-map-resolved frames in its UI — neither is
checkable without one.
"""

from typing import Any

import sentry_sdk

from keel.core.sentry import init_sentry, report_exception
from keel.core.tests.sentry_stub import CapturingTransport


def _init_with_stub(**overrides: Any) -> CapturingTransport:
    transport = CapturingTransport()
    init_sentry(transport=transport, **overrides)
    return transport


def teardown_function() -> None:
    # Restores the ordinary no-op client (test settings' SENTRY_DSN is
    # blank) so a captured-transport client from one test never leaks
    # into another.
    init_sentry()


def test_report_exception_captures_the_exception_type_and_message() -> None:
    transport = _init_with_stub(release="abc123", environment="test")

    try:
        raise ValueError("boom")
    except ValueError as exc:
        report_exception(exc)

    sentry_sdk.get_client().flush()
    assert len(transport.envelopes) == 1
    event = transport.envelopes[0].get_event()
    assert event is not None
    exception_values = event["exception"]["values"]
    assert exception_values[-1]["type"] == "ValueError"
    assert exception_values[-1]["value"] == "boom"
    # A readable stack — frames with file/line info, not just a message
    # (PRD's "readable stack" criterion).
    assert exception_values[-1]["stacktrace"]["frames"]


def test_report_exception_tags_the_event() -> None:
    transport = _init_with_stub(release="abc123", environment="test")

    try:
        raise RuntimeError("dead-lettered")
    except RuntimeError as exc:
        report_exception(exc, tags={"task_name": "keel.widgets.tasks.notify_widget_created_task"})

    sentry_sdk.get_client().flush()
    event = transport.envelopes[0].get_event()
    assert event["tags"]["task_name"] == "keel.widgets.tasks.notify_widget_created_task"


def test_release_is_tied_to_the_configured_git_sha() -> None:
    transport = _init_with_stub(release="a1b2c3d4", environment="production")

    try:
        raise ValueError("release check")
    except ValueError as exc:
        report_exception(exc)

    sentry_sdk.get_client().flush()
    event = transport.envelopes[0].get_event()
    assert event["release"] == "a1b2c3d4"
    assert event["environment"] == "production"


def test_init_sentry_is_a_no_op_without_a_dsn(settings: Any) -> None:
    """The default state in this project (no DSN) — sentry_sdk.init()
    with dsn=None leaves the client with no transport, so
    capture_exception has nowhere to send to and is a safe no-op —
    every call site (report_to_sentry, report_exception) stays callable
    regardless of whether a DSN is configured."""
    settings.SENTRY_DSN = ""
    init_sentry()

    assert sentry_sdk.get_client().transport is None
