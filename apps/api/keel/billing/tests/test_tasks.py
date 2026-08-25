"""``dispatch_stripe_event`` / ``process_stripe_event`` (docs/plans/phase-4.md
B.3): atomic dispatch, unhandled event types are marked processed as a
no-op, a raising handler records ``StripeEvent.error`` and retries, and an
already-processed event is a no-op on redelivery."""

import pytest

from keel.billing import tasks, webhooks
from keel.billing.models import StripeEvent

pytestmark = pytest.mark.django_db


def _stripe_event(event_id: str = "evt_1", event_type: str = "invoice.paid") -> StripeEvent:
    return StripeEvent.objects.create(
        id=event_id,
        type=event_type,
        payload={"id": event_id, "type": event_type, "data": {"object": {"customer": "cus_x"}}},
    )


def test_process_stripe_event_marks_unhandled_type_processed_as_a_noop() -> None:
    stripe_event = _stripe_event(event_type="payment_intent.succeeded")

    tasks.process_stripe_event(stripe_event)

    stripe_event.refresh_from_db()
    assert stripe_event.processed_at is not None
    assert stripe_event.error == ""


def test_process_stripe_event_is_a_noop_when_already_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stripe_event = _stripe_event()
    calls = []
    monkeypatch.setitem(webhooks.HANDLERS, "invoice.paid", lambda obj: calls.append(obj))
    tasks.process_stripe_event(stripe_event)
    assert calls == [{"customer": "cus_x"}]

    tasks.process_stripe_event(stripe_event)

    assert calls == [{"customer": "cus_x"}], "a processed event must not be handled again"


def test_process_stripe_event_leaves_it_unprocessed_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``process_stripe_event`` itself just raises — recording
    ``StripeEvent.error`` and deciding whether to retry is
    ``dispatch_stripe_event``'s job, exercised below."""
    stripe_event = _stripe_event()

    def _boom(obj):
        raise ValueError("organisation not found")

    monkeypatch.setitem(webhooks.HANDLERS, "invoice.paid", _boom)

    with pytest.raises(ValueError):
        tasks.process_stripe_event(stripe_event)

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

    def _always_fails(obj):
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
