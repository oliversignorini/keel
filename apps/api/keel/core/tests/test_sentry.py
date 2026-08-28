"""Sentry wiring (PRD §4 Integration points).

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

from keel.core.sentry import init_sentry, report_exception, report_message, scrub_event
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


def test_report_message_captures_the_message_and_tags() -> None:
    """The non-exception seam (ddia#4) — a beat task can report a fact
    about state (e.g. credit balance drift) with no exception to attach."""
    transport = _init_with_stub(release="abc123", environment="test")

    report_message(
        "Credit balance drift detected for organisation org-1",
        level="warning",
        tags={"organization_id": "org-1"},
    )

    sentry_sdk.get_client().flush()
    assert len(transport.envelopes) == 1
    event = transport.envelopes[0].get_event()
    assert event["message"] == "Credit balance drift detected for organisation org-1"
    assert event["level"] == "warning"
    assert event["tags"]["organization_id"] == "org-1"


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


# --- Redaction ("before_send scrubber ... test it with a payload
# containing each secret type") -----------------------------------------


def test_scrub_event_redacts_request_headers_cookies_and_body() -> None:
    event = {
        "request": {
            "headers": {"Authorization": "Bearer abc123", "Content-Type": "application/json"},
            "cookies": {"sessionid": "sess-abc", "csrftoken": "csrf-abc"},
            "data": {
                "password": "hunter2",
                "stripe_signature": "t=1,v1=deadbeef",
                "email": "dev@example.com",
            },
        }
    }

    scrubbed = scrub_event(event, {})

    request = scrubbed["request"]
    assert request["headers"]["Authorization"] == "[REDACTED]"
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["cookies"]["sessionid"] == "[REDACTED]"
    assert request["cookies"]["csrftoken"] == "[REDACTED]"
    assert request["data"]["password"] == "[REDACTED]"
    assert request["data"]["stripe_signature"] == "[REDACTED]"
    assert request["data"]["email"] == "dev@example.com"


def test_scrub_event_redacts_extra_contexts_and_breadcrumbs() -> None:
    event = {
        "extra": {"api_key": "sk_live_abcdef", "organization_id": "org-1"},
        "contexts": {"oauth": {"access_token": "at-1", "refresh_token": "rt-1"}},
        "breadcrumbs": {"values": [{"message": "called", "data": {"password": "hunter2"}}]},
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed["extra"]["api_key"] == "[REDACTED]"
    assert scrubbed["extra"]["organization_id"] == "org-1"
    assert scrubbed["contexts"]["oauth"]["access_token"] == "[REDACTED]"
    assert scrubbed["contexts"]["oauth"]["refresh_token"] == "[REDACTED]"
    assert scrubbed["breadcrumbs"]["values"][0]["data"]["password"] == "[REDACTED]"


def test_scrub_event_is_a_no_op_on_an_event_with_none_of_those_sections() -> None:
    event = {"message": "plain event"}

    assert scrub_event(event, {}) == {"message": "plain event"}


def test_before_send_is_wired_and_redacts_a_real_captured_event() -> None:
    """End-to-end through sentry_sdk.init(before_send=...), not the
    function directly — proves the wiring, not just the function."""
    transport = _init_with_stub(release="abc123", environment="test")

    with sentry_sdk.new_scope() as scope:
        scope.set_extra("api_key", "sk_live_abcdef")
        scope.set_extra("organization_id", "org-1")
        try:
            raise ValueError("boom")
        except ValueError as exc:
            report_exception(exc)

    sentry_sdk.get_client().flush()
    event = transport.envelopes[0].get_event()
    assert event["extra"]["api_key"] == "[REDACTED]"
    assert event["extra"]["organization_id"] == "org-1"


def test_init_sentry_is_a_no_op_without_a_dsn(settings: Any) -> None:
    """The default state in this project (no DSN) — sentry_sdk.init()
    with dsn=None leaves the client with no transport, so
    capture_exception has nowhere to send to and is a safe no-op —
    every call site (report_to_sentry, report_exception) stays callable
    regardless of whether a DSN is configured."""
    settings.SENTRY_DSN = ""
    init_sentry()

    assert sentry_sdk.get_client().transport is None
