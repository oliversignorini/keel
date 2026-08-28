"""The Stripe webhook worker (PRD §6 "Stripe webhook"): "atomic dispatch
to the handler, upsert Subscription, retry with backoff x5, then
StripeEvent.error plus a Sentry event."

Uses Celery directly rather than ``keel.core.tasks``'s Tier-1 shim: that
shim is explicitly fire-and-forget with no retry surface, and this worker
needs bound retries with backoff — the shim's own docstring says exactly
this class of need "needs Celery's actual surface, used directly" rather
than growing the shim to cover it.

Retry/backoff here is deliberately simple (exponential, no dead-letter
queue): the generic ``FailedTask`` row and dead-letter mechanism PRD §5
"Scheduled jobs" describes live in ``keel/jobs/`` and this worker doesn't
use them. An event that exhausts its retries lands with
``StripeEvent.error`` set and ``processed_at`` still null — inspectable
and re-processable by hand via Django admin.

Also holds ``sync_seat_quantity_task`` (B.5), which *does* use the Tier-1
shim — see its own docstring for why the two tasks in this module use
different mechanisms.
"""

from datetime import timedelta
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from keel.billing.models import StripeEvent
from keel.billing.webhooks import HANDLERS
from keel.core.tasks import task

MAX_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 5
STALE_EVENT_THRESHOLD = timedelta(minutes=5)
STRIPE_EVENT_PAYLOAD_RETENTION = timedelta(days=30)


def _report_to_sentry(stripe_event: StripeEvent, exc: Exception) -> None:
    """Wired to the real SDK (PRD §5, "then StripeEvent.error plus a
    Sentry event") via ``keel.core.sentry``, which is itself a no-op
    without a DSN — see that module's docstring."""
    from keel.core.sentry import report_exception

    report_exception(
        exc,
        tags={"stripe_event_id": str(stripe_event.pk), "stripe_event_type": stripe_event.type},
    )


def process_stripe_event(stripe_event: StripeEvent) -> None:
    """Atomic dispatch to the handler for ``stripe_event.type``, then marks
    it processed. A replay of an already-processed event (``processed_at``
    set) is a no-op — the second line of idempotency defense behind the
    view's ``get_or_create`` (PRD §6, "Replaying an event is a no-op by
    construction"). An unhandled event type is marked processed without
    doing anything, since PRD §6 only lists six event types as handled.

    The "already processed" guard is a lock, not a plain read (ddia#8):
    two workers processing the same event concurrently (Celery is
    at-least-once, and the view's re-enqueue-on-replay adds a second path
    to the same race) must not both run the handler — a
    ``select_for_update`` inside the same transaction as the check makes
    the second one block until the first commits, then see
    ``processed_at`` already set."""
    with transaction.atomic():
        stripe_event = StripeEvent.objects.select_for_update().get(pk=stripe_event.pk)
        if stripe_event.processed_at is not None:
            return
        handler = HANDLERS.get(stripe_event.type)
        if handler is not None:
            handler(stripe_event.payload["data"]["object"], stripe_event.payload.get("created"))
        stripe_event.processed_at = timezone.now()
        stripe_event.error = ""
        stripe_event.save(update_fields=["processed_at", "error"])


@shared_task(bind=True, max_retries=MAX_RETRIES)
def dispatch_stripe_event(self: Any, event_id: str) -> None:
    stripe_event = StripeEvent.objects.get(pk=event_id)
    try:
        process_stripe_event(stripe_event)
    except Exception as exc:
        stripe_event.error = str(exc)
        stripe_event.save(update_fields=["error"])
        if self.request.retries >= self.max_retries:
            _report_to_sentry(stripe_event, exc)
            return
        raise self.retry(
            exc=exc, countdown=RETRY_BACKOFF_BASE_SECONDS * (2**self.request.retries)
        ) from exc


@shared_task(name="keel.billing.tasks.sweep_unprocessed_stripe_events")
def sweep_unprocessed_stripe_events() -> int:
    """Beat sweeper (ddia#7): catches the case the view's re-enqueue can't
    — a ``StripeEvent`` row that committed but whose ``.delay()`` never
    reached the broker at all, so no redelivery from Stripe will ever
    re-trigger the view's own re-enqueue path (Stripe only retries on a
    non-200, and the view always returns 200). Re-dispatches any row
    still unprocessed ``STALE_EVENT_THRESHOLD`` after receipt —
    ``process_stripe_event`` is a no-op if another worker already handled
    it in the meantime."""
    threshold = timezone.now() - STALE_EVENT_THRESHOLD
    stale_ids = list(
        StripeEvent.objects.filter(
            processed_at__isnull=True, received_at__lt=threshold
        ).values_list("pk", flat=True)
    )
    for event_id in stale_ids:
        dispatch_stripe_event.delay(event_id)
    return len(stale_ids)


@shared_task(name="keel.billing.tasks.prune_stripe_event_payloads")
def prune_stripe_event_payloads() -> int:
    """Beat task (ddia#10): ``StripeEvent.payload`` is the write-ahead log
    for billing state and grows monotonically with no retention — table
    bloat, vacuum pressure on the hottest billing table, and indefinite
    retention of whatever PII a Stripe event carries. Nulls ``payload``
    on rows older than ``STRIPE_EVENT_PAYLOAD_RETENTION`` that have
    already been processed, keeping id/type/timestamps — the dedup key —
    intact. An unprocessed row is never touched: it may still be replayed
    by ``sweep_unprocessed_stripe_events`` or retried by
    ``dispatch_stripe_event``, both of which need the payload."""
    threshold = timezone.now() - STRIPE_EVENT_PAYLOAD_RETENTION
    return (
        StripeEvent.objects.filter(processed_at__isnull=False, received_at__lt=threshold)
        .exclude(payload={})
        .update(payload={})
    )


@shared_task(name="keel.billing.tasks.check_credit_balances_task")
def check_credit_balances_task() -> int:
    """Beat task (ddia#4): the nightly, read-only counterpart to
    ``manage.py rebuild_credit_balances --check`` — reports drift via
    Sentry, never repairs it. Repair stays a manual, operator-run command
    so a human decides before anything gets rewritten; a scheduled task
    that both detects *and* silently repairs would erase the evidence of
    whatever bug caused the drift in the first place."""
    from keel.billing.services import check_credit_balances
    from keel.core.sentry import report_message

    drifted = check_credit_balances()
    for row in drifted:
        report_message(
            "Credit balance drift detected for organisation "
            f"{row['organization_id']}: ledger={row['ledger_total']} "
            f"balance={row['balance']}",
            level="warning",
            tags={"organization_id": row["organization_id"]},
        )
    return len(drifted)


@task
def sync_seat_quantity_task(organization_id: str) -> None:
    """Tier-1 fire-and-forget dispatch — this
    is exactly the shim's own canonical example, "sync a Stripe object".
    Unlike the webhook worker above, no retry is needed here: the next
    membership create/remove re-syncs to the correct count regardless of
    whether this particular sync succeeded, so there's nothing to retry
    that the next event doesn't already fix. Takes an id, never a model
    instance (PRD §5, "every task takes IDs")."""
    from keel.billing.services import sync_seat_quantity
    from keel.organizations.models import Organization

    organization = Organization.objects.get(pk=organization_id)
    sync_seat_quantity(organization)
