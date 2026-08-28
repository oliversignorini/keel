"""``dispatch_stripe_event`` (``keel.billing.tasks``) over
``process_stripe_event`` (``keel.billing.services``):
atomic dispatch, unhandled event types are marked processed as a
no-op, a raising handler records ``StripeEvent.error`` and retries, and an
already-processed event is a no-op on redelivery."""

from datetime import timedelta

import pytest
import sentry_sdk
from django.utils import timezone

from keel.billing import credits, selectors, services, tasks, webhooks
from keel.billing.models import CreditBalance, StripeEvent
from keel.billing.tests.factories import make_organization
from keel.core.sentry import init_sentry
from keel.core.tests.sentry_stub import CapturingTransport

pytestmark = pytest.mark.django_db


def _stripe_event(event_id: str = "evt_1", event_type: str = "invoice.paid") -> StripeEvent:
    return StripeEvent.objects.create(
        id=event_id,
        type=event_type,
        payload={"id": event_id, "type": event_type, "data": {"object": {"customer": "cus_x"}}},
    )


def test_process_stripe_event_marks_unhandled_type_processed_as_a_noop() -> None:
    stripe_event = _stripe_event(event_type="payment_intent.succeeded")

    services.process_stripe_event(stripe_event)

    stripe_event.refresh_from_db()
    assert stripe_event.processed_at is not None
    assert stripe_event.error == ""


def test_process_stripe_event_is_a_noop_when_already_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stripe_event = _stripe_event()
    calls = []
    monkeypatch.setitem(webhooks.HANDLERS, "invoice.paid", lambda obj, created: calls.append(obj))
    services.process_stripe_event(stripe_event)
    assert calls == [{"customer": "cus_x"}]

    services.process_stripe_event(stripe_event)

    assert calls == [{"customer": "cus_x"}], "a processed event must not be handled again"


def test_process_stripe_event_leaves_it_unprocessed_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``process_stripe_event`` itself just raises — recording
    ``StripeEvent.error`` and deciding whether to retry is
    ``dispatch_stripe_event``'s job, exercised below."""
    stripe_event = _stripe_event()

    def _boom(obj, created):
        raise ValueError("organisation not found")

    monkeypatch.setitem(webhooks.HANDLERS, "invoice.paid", _boom)

    with pytest.raises(ValueError):
        services.process_stripe_event(stripe_event)

    stripe_event.refresh_from_db()
    assert stripe_event.processed_at is None
    assert stripe_event.error == ""


def test_dispatch_stripe_event_retries_then_gives_up_after_max_retries(
    monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    stripe_event = _stripe_event()
    attempts = []

    def _always_fails(obj, created):
        attempts.append(1)
        raise ValueError("stripe is down")

    monkeypatch.setitem(webhooks.HANDLERS, "invoice.paid", _always_fails)
    reported = []
    monkeypatch.setattr(tasks, "_report_to_sentry", lambda event, exc: reported.append(exc))

    tasks.dispatch_stripe_event.apply(args=[stripe_event.pk], throw=False)

    assert len(attempts) == tasks.MAX_RETRIES + 1
    assert len(reported) == 1
    stripe_event.refresh_from_db()
    assert stripe_event.processed_at is None
    assert "stripe is down" in stripe_event.error


def test_dispatch_stripe_event_exhaustion_reports_to_sentry_with_the_real_sdk(
    monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    """The real path, not the monkeypatched
    ``_report_to_sentry`` the test above uses to isolate retry counting."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    stripe_event = _stripe_event(event_id="evt_sentry")

    def _always_fails(obj, created):
        raise ValueError("stripe is really down")

    monkeypatch.setitem(webhooks.HANDLERS, "invoice.paid", _always_fails)

    transport = CapturingTransport()
    init_sentry(transport=transport, release="test-sha")
    try:
        tasks.dispatch_stripe_event.apply(args=[stripe_event.pk], throw=False)
        sentry_sdk.get_client().flush()
    finally:
        init_sentry()

    assert len(transport.envelopes) == 1
    event = transport.envelopes[0].get_event()
    assert event["exception"]["values"][-1]["type"] == "ValueError"
    assert event["tags"]["stripe_event_id"] == "evt_sentry"


# --- sweep_unprocessed_stripe_events (ddia#7) -------------------------------


def test_sweeper_redispatches_only_stale_unprocessed_events(monkeypatch) -> None:
    """The stale-row query is a selector now; the task keeps only the
    enqueue direction. Both halves are asserted here: which ids the
    selector reports, and that the task dispatches exactly those."""
    stale = _stripe_event(event_id="evt_stale")
    StripeEvent.objects.filter(pk=stale.pk).update(
        received_at=timezone.now() - selectors.STALE_EVENT_THRESHOLD - timedelta(minutes=1)
    )
    _stripe_event(event_id="evt_fresh")
    processed = _stripe_event(event_id="evt_done")
    StripeEvent.objects.filter(pk=processed.pk).update(
        processed_at=timezone.now(),
        received_at=timezone.now() - selectors.STALE_EVENT_THRESHOLD - timedelta(minutes=1),
    )

    assert selectors.stale_unprocessed_stripe_event_ids() == ["evt_stale"]

    dispatched: list[str] = []
    monkeypatch.setattr(
        tasks.dispatch_stripe_event, "delay", lambda event_id: dispatched.append(event_id)
    )

    assert tasks.sweep_unprocessed_stripe_events() == 1
    assert dispatched == ["evt_stale"]


# --- prune_stripe_event_payloads (ddia#10) ----------------------------------


def test_prune_nulls_the_payload_of_old_processed_events() -> None:
    old = _stripe_event(event_id="evt_old")
    StripeEvent.objects.filter(pk=old.pk).update(
        processed_at=timezone.now(),
        received_at=timezone.now() - services.STRIPE_EVENT_PAYLOAD_RETENTION - timedelta(days=1),
    )

    pruned = tasks.prune_stripe_event_payloads()

    old.refresh_from_db()
    assert pruned == 1
    assert old.payload == {}
    assert old.type == "invoice.paid"  # the dedup key survives


def test_prune_leaves_recent_processed_events_alone() -> None:
    recent = _stripe_event(event_id="evt_recent")
    StripeEvent.objects.filter(pk=recent.pk).update(processed_at=timezone.now())

    pruned = tasks.prune_stripe_event_payloads()

    recent.refresh_from_db()
    assert pruned == 0
    assert recent.payload != {}


def test_prune_leaves_unprocessed_events_alone_regardless_of_age() -> None:
    """An unprocessed row may still be replayed by
    ``sweep_unprocessed_stripe_events`` or retried by
    ``dispatch_stripe_event`` — both need the payload."""
    unprocessed = _stripe_event(event_id="evt_unprocessed")
    StripeEvent.objects.filter(pk=unprocessed.pk).update(
        received_at=timezone.now() - services.STRIPE_EVENT_PAYLOAD_RETENTION - timedelta(days=1)
    )

    pruned = tasks.prune_stripe_event_payloads()

    unprocessed.refresh_from_db()
    assert pruned == 0
    assert unprocessed.payload != {}


# --- check_credit_balances_task (ddia#4) ------------------------------------


def test_check_credit_balances_task_reports_drift_via_sentry() -> None:
    org = make_organization()
    credits.grant(org, 40)
    CreditBalance.objects.filter(organization=org).update(balance=999)

    transport = CapturingTransport()
    init_sentry(transport=transport, release="test-sha")
    try:
        count = tasks.check_credit_balances_task()
        sentry_sdk.get_client().flush()
    finally:
        init_sentry()

    assert count == 1
    assert len(transport.envelopes) == 1
    event = transport.envelopes[0].get_event()
    assert str(org.id) in event["message"]
    assert event["level"] == "warning"
    assert CreditBalance.objects.get(organization=org).balance == 999  # never repaired


def test_check_credit_balances_task_reports_nothing_when_no_drift() -> None:
    org = make_organization()
    credits.grant(org, 40)

    transport = CapturingTransport()
    init_sentry(transport=transport, release="test-sha")
    try:
        count = tasks.check_credit_balances_task()
        sentry_sdk.get_client().flush()
    finally:
        init_sentry()

    assert count == 0
    assert transport.envelopes == []
