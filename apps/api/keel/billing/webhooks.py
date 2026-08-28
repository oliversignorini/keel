"""Stripe webhook handlers (PRD §6 "Stripe webhook"). Each handler takes
the Stripe object embedded at
``event["data"]["object"]`` — a plain dict, the shape ``StripeEvent.payload``
stores it in — and is idempotent by construction: replaying the same event
twice must leave state identical, since Stripe redelivers on a timeout even
after a handler already succeeded.

Handled events (PRD §6): ``checkout.session.completed``,
``customer.subscription.created|updated|deleted``, ``invoice.paid``,
``invoice.payment_failed``.
"""

from datetime import UTC, datetime
from typing import Any

from keel.billing.models import Price, Subscription
from keel.core.posthog import capture_billing_event
from keel.organizations.models import Organization


def _parse_timestamp(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def _handle_checkout_completed(session: dict[str, Any], event_created: int | None) -> None:
    """No-op by design: Stripe fires ``customer.subscription.created``
    immediately after a successful Checkout, and that event — not this
    one — carries the actual subscription line items. Recommended Stripe
    pattern is to treat subscription events as the source of truth and
    use ``checkout.session.completed`` only for one-time-payment or
    session-correlation flows this template doesn't have. Recorded here
    (and idempotency-tracked via ``StripeEvent``) purely because PRD §6
    lists it as a handled event type."""


def _handle_subscription_event(subscription: dict[str, Any], event_created: int | None) -> None:
    """Upserts the ``Subscription`` row for ``customer.subscription.
    created|updated|deleted`` — Stripe sends the full subscription object
    (with ``status: "canceled"``) on deletion too, so one handler covers
    all three. Keyed on ``organization`` (the OneToOne side), not
    ``stripe_subscription_id``: a cancel-then-resubscribe must update the
    same row, not violate the one-subscription-per-organization
    constraint by inserting a second.

    LWW version guard (ddia#9): Stripe guarantees neither delivery order
    nor at-most-once delivery, so an unconditional ``update_or_create``
    lets an older, late-delivered event overwrite a newer one — e.g.
    ``customer.subscription.updated`` landing after
    ``customer.subscription.deleted`` resurrects a cancelled
    subscription. ``event_created`` (the *event's* own timestamp, not
    anything inside the subscription object) is compared against the
    row's ``stripe_updated_at``; a write only applies when it is newer.
    ``event_created`` is only absent for a payload built by hand (a test
    fixture), never a real Stripe delivery — the guard is a no-op then,
    matching the pre-ddia#9 behaviour rather than refusing to apply
    anything."""
    organization = Organization.objects.get(stripe_customer_id=subscription["customer"])
    item = subscription["items"]["data"][0]
    price = Price.objects.select_related("plan").get(stripe_price_id=item["price"]["id"])
    incoming_updated_at = _parse_timestamp(event_created)

    existing = Subscription.objects.select_for_update().filter(organization=organization).first()
    if (
        existing is not None
        and existing.stripe_updated_at is not None
        and incoming_updated_at is not None
        and incoming_updated_at <= existing.stripe_updated_at
    ):
        return  # stale/out-of-order delivery: a newer event already applied

    Subscription.objects.update_or_create(
        organization=organization,
        defaults={
            "stripe_subscription_id": subscription["id"],
            "plan": price.plan,
            "price": price,
            "status": subscription["status"],
            "quantity": item.get("quantity", 1),
            "current_period_end": _parse_timestamp(subscription.get("current_period_end")),
            "trial_end": _parse_timestamp(subscription.get("trial_end")),
            "cancel_at_period_end": bool(subscription.get("cancel_at_period_end", False)),
            "stripe_updated_at": incoming_updated_at,
        },
    )
    capture_billing_event(
        distinct_id=str(organization.created_by_id),
        event=f"subscription_{subscription['status']}",
        properties={
            "organization_id": str(organization.id),
            "plan_code": price.plan.code,
            "stripe_subscription_id": subscription["id"],
        },
    )


def _handle_invoice_paid(invoice: dict[str, Any], event_created: int | None) -> None:
    """Clears dunning: a paid invoice means the
    organisation is no longer past due. No-op if there's no local
    ``Subscription`` row yet — e.g. the very first invoice on a trial
    that never required payment.

    Only transitions ``past_due`` → ``active`` (ddia#9): the previous
    unconditional ``.update(status="active")`` clobbered every status for
    the customer — ``canceled``, ``trialing``, ``incomplete`` alike. A
    cancelled organisation that receives a late ``invoice.paid`` must not
    become ``active`` and get its plan entitlements back."""
    Subscription.objects.filter(
        organization__stripe_customer_id=invoice["customer"], status="past_due"
    ).update(status="active")
    organization = Organization.objects.filter(stripe_customer_id=invoice["customer"]).first()
    if organization is not None:
        capture_billing_event(
            distinct_id=str(organization.created_by_id),
            event="invoice_paid",
            properties={"organization_id": str(organization.id)},
        )


def _handle_invoice_payment_failed(invoice: dict[str, Any], event_created: int | None) -> None:
    """Puts the organisation into a dunning state. This is the state the
    banner reads, and access is deliberately *not* revoked here — a failed
    payment degrades to a warning, not a lockout."""
    Subscription.objects.filter(organization__stripe_customer_id=invoice["customer"]).update(
        status="past_due"
    )
    organization = Organization.objects.filter(stripe_customer_id=invoice["customer"]).first()
    if organization is not None:
        capture_billing_event(
            distinct_id=str(organization.created_by_id),
            event="invoice_payment_failed",
            properties={"organization_id": str(organization.id)},
        )


HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "customer.subscription.created": _handle_subscription_event,
    "customer.subscription.updated": _handle_subscription_event,
    "customer.subscription.deleted": _handle_subscription_event,
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_failed": _handle_invoice_payment_failed,
}
