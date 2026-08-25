"""The Stripe webhook worker (PRD §6 "Stripe webhook"; docs/plans/phase-4.md
B.3): "atomic dispatch to the handler, upsert Subscription, retry with
backoff x5, then StripeEvent.error plus a Sentry event."

Uses Celery directly rather than ``keel.core.tasks``'s Tier-1 shim: that
shim is explicitly fire-and-forget with no retry surface, and this worker
needs bound retries with backoff — the shim's own docstring says exactly
this class of need "needs Celery's actual surface, used directly" rather
than growing the shim to cover it.

Retry/backoff here is deliberately simple (exponential, no dead-letter
queue): PRD §5 "Scheduled jobs" lists a ``FailedTask`` row and a generic
dead-letter mechanism as Phase 5 deliverables, not Phase 4's. An event
that exhausts its retries lands with ``StripeEvent.error`` set and
``processed_at`` still null — inspectable and re-processable by hand via
Django admin, re-drivable properly once Phase 5's mechanism exists.

Also holds ``sync_seat_quantity_task`` (B.5), which *does* use the Tier-1
shim — see its own docstring for why the two tasks in this module use
different mechanisms.
"""

from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from keel.billing.models import StripeEvent
from keel.billing.webhooks import HANDLERS
from keel.core.tasks import task

MAX_RETRIES = 5
RETRY_BACKOFF_BASE_SECONDS = 5


def _report_to_sentry(stripe_event: StripeEvent, exc: Exception) -> None:
    """Seam for Sentry (PRD §5, "then StripeEvent.error plus a Sentry
    event"). Sentry SDK isn't wired into this project yet (a later phase's
    task per the PRD's infra list) — documented no-op until then, same
    pattern as ``organizations/services.py``'s ``_sync_stripe_customer``."""


def process_stripe_event(stripe_event: StripeEvent) -> None:
    """Atomic dispatch to the handler for ``stripe_event.type``, then marks
    it processed. A replay of an already-processed event (``processed_at``
    set) is a no-op — the second line of idempotency defense behind the
    view's ``get_or_create`` (PRD §6, "Replaying an event is a no-op by
    construction"). An unhandled event type is marked processed without
    doing anything, since PRD §6 only lists six event types as handled."""
    stripe_event.refresh_from_db()
    if stripe_event.processed_at is not None:
        return
    handler = HANDLERS.get(stripe_event.type)
    with transaction.atomic():
        if handler is not None:
            handler(stripe_event.payload["data"]["object"])
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


@task
def sync_seat_quantity_task(organization_id: str) -> None:
    """Tier-1 fire-and-forget dispatch (docs/plans/phase-4.md B.5) — this
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
