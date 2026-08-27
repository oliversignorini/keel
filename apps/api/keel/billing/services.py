"""Billing services (docs/plans/phase-4.md B.1-B.6). Starts with plan/price
sync — the part that is pure arithmetic over rows, same shape as
``organizations/services.py``: one function per operation, transactional,
no Stripe I/O inside it (``stripe_client.py`` owns that seam)."""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from keel.billing import stripe_client
from keel.billing.entitlements import enforce_downgrade_limits
from keel.billing.models import CreditBalance, CreditLedgerEntry, Plan, Price, Subscription
from keel.core.audit import audited, not_audited
from keel.core.impersonation import forbid_when_impersonating
from keel.organizations.models import Membership, Organization

CHECKOUT_TRIAL_DAYS = 14
TRIAL_ENDING_NOTICE_WINDOW_DAYS = 3


class MissingPlanCode(Exception):
    """A Stripe Product with no ``metadata.code`` cannot become a Plan —
    ``Plan.code`` is what the rest of the app (entitlements, seat sync,
    the pricing page) addresses a plan by, and Stripe assigns no equivalent
    stable, human-chosen slug on its own."""

    def __init__(self, stripe_product_id: str) -> None:
        self.stripe_product_id = stripe_product_id
        super().__init__(
            f"Stripe product {stripe_product_id!r} has no metadata['code']. "
            "Set a 'code' metadata key on the product in Stripe before syncing."
        )


@not_audited(
    reason="System-driven catalogue sync from Stripe (management command / nightly "
    "beat job), not a user action — no actor. Stripe is already the source of "
    "truth for plans and prices; this mirrors it, it doesn't decide anything."
)
@transaction.atomic
def sync_plans_from_stripe(products: list[dict[str, Any]]) -> dict[str, int]:
    """Upsert ``Plan``/``Price`` rows from ``products`` — the normalised
    shape ``stripe_client.fetch_products_and_prices`` returns. Stripe is the
    source of truth: a plan or price no longer present and active in
    ``products`` is deactivated locally, never deleted (other rows —
    ``Subscription``, ``CreditLedgerEntry`` — reference these by FK).

    Returns counts for the management command to report.
    """
    seen_product_ids: set[str] = set()
    seen_price_ids: set[str] = set()
    plans_synced = 0
    prices_synced = 0

    for product in products:
        stripe_product_id = product["id"]
        code = product.get("metadata", {}).get("code")
        if not code:
            raise MissingPlanCode(stripe_product_id)
        seen_product_ids.add(stripe_product_id)

        plan, _ = Plan.objects.update_or_create(
            stripe_product_id=stripe_product_id,
            defaults={"code": code, "name": product["name"], "is_active": True},
        )
        plans_synced += 1

        for price in product.get("prices", []):
            stripe_price_id = price["id"]
            interval = price.get("recurring", {}).get("interval", Price.INTERVAL_MONTH)
            seen_price_ids.add(stripe_price_id)
            Price.objects.update_or_create(
                stripe_price_id=stripe_price_id,
                defaults={
                    "plan": plan,
                    "interval": interval,
                    "unit_amount": price["unit_amount"],
                    "currency": price["currency"].upper(),
                    "is_active": True,
                },
            )
            prices_synced += 1

    deactivated_plans = (
        Plan.objects.exclude(stripe_product_id="")
        .exclude(stripe_product_id__in=seen_product_ids)
        .filter(is_active=True)
        .update(is_active=False)
    )
    deactivated_prices = (
        Price.objects.exclude(stripe_price_id__in=seen_price_ids)
        .filter(is_active=True)
        .update(is_active=False)
    )

    return {
        "plans_synced": plans_synced,
        "prices_synced": prices_synced,
        "plans_deactivated": deactivated_plans,
        "prices_deactivated": deactivated_prices,
    }


@not_audited(
    reason="Internal helper called by create_checkout_session and "
    "create_portal_session, both of which are audited — decorating this too "
    "would double-record a single checkout/portal call as two audit rows."
)
def ensure_stripe_customer(organization: Organization) -> str:
    """Lazily creates the Stripe customer for ``organization`` on first
    need and persists the id. No ``transaction.atomic()`` here (PRD §4,
    "No Stripe call happens inside an open transaction", invariant 3):
    the Stripe call happens first, and the local write that follows it is
    a single-field save, not a multi-step block that needs wrapping."""
    if organization.stripe_customer_id:
        return organization.stripe_customer_id
    customer_id = stripe_client.create_customer(
        email=organization.created_by.email, name=organization.name
    )
    organization.stripe_customer_id = customer_id
    organization.save(update_fields=["stripe_customer_id"])
    return customer_id


@audited("billing.checkout_session_created")
def create_checkout_session(
    *,
    organization: Organization,
    actor: Any,
    price: Price,
    success_url: str,
    cancel_url: str,
    impersonator: Any = None,
) -> str:
    """``POST /orgs/<org_slug>/billing/checkout/``
    (docs/plans/phase-4.md B.2). Returns the Checkout Session URL — the
    ``Subscription`` row itself is created later, by the webhook handler
    processing ``checkout.session.completed``, not here.

    If the organisation already has a subscription, this doubles as the
    plan-change entry point — Checkout replaces an existing subscription's
    price when reused this way. A downgrade whose target plan's limits
    are already exceeded by current usage is blocked before any Stripe
    call (docs/plans/phase-4.md B.4).

    Covers both halves of PRD §6's "start or cancel a subscription"
    restriction for impersonated sessions — starting and plan-changing
    both go through this one entry point."""
    forbid_when_impersonating(impersonator, "start or change a subscription")
    existing_subscription = Subscription.objects.filter(organization=organization).first()
    if existing_subscription is not None:
        enforce_downgrade_limits(organization, price.plan)
    customer_id = ensure_stripe_customer(organization)
    return stripe_client.create_checkout_session(
        customer_id=customer_id,
        price_id=price.stripe_price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        trial_period_days=CHECKOUT_TRIAL_DAYS,
    )


@audited("billing.portal_session_created")
def create_portal_session(
    *, organization: Organization, actor: Any, return_url: str, impersonator: Any = None
) -> str:
    """``POST /orgs/<org_slug>/billing/portal/``
    (docs/plans/phase-4.md B.2). Returns the Customer Portal URL — the
    Stripe Customer Portal is where a subscription is cancelled (PRD §4
    "Billing flow"), so this is the other half of PRD §6's "start or
    cancel a subscription" restriction for impersonated sessions."""
    forbid_when_impersonating(impersonator, "start or cancel a subscription")
    customer_id = ensure_stripe_customer(organization)
    return stripe_client.create_billing_portal_session(
        customer_id=customer_id, return_url=return_url
    )


@not_audited(
    reason="System-triggered from transaction.on_commit() by "
    "accept_invitation/remove_member, both of which already audit the "
    "membership change that caused this — recording it again here would be "
    "a second row for the same event with no actor of its own."
)
def sync_seat_quantity(organization: Organization) -> None:
    """Syncs active membership count to the organisation's Stripe
    subscription quantity, with proration (docs/plans/phase-4.md B.5).
    A no-op if the organisation has no ``Subscription`` yet — seat pricing
    can be on before anyone has checked out."""
    subscription = Subscription.objects.filter(organization=organization).first()
    if subscription is None:
        return
    quantity = Membership.objects.filter(
        organization=organization, status=Membership.STATUS_ACTIVE
    ).count()
    stripe_client.update_subscription_quantity(
        subscription_id=subscription.stripe_subscription_id, quantity=quantity
    )
    subscription.quantity = quantity
    subscription.save(update_fields=["quantity"])


@not_audited(
    reason="Scheduled system job / management command entry point; wraps "
    "sync_plans_from_stripe, which carries the same not_audited reasoning."
)
def sync_stripe_plans() -> dict[str, int]:
    """The nightly Stripe plan sync (PRD §5 "Scheduled jobs";
    docs/plans/phase-5.md 5.4). Wraps fetch-then-upsert as one call so
    the scheduled task's body stays a single service call — the
    management command (``sync_stripe_plans``) uses this too, so there
    is exactly one place that sequence is spelled out."""
    products = stripe_client.fetch_products_and_prices()
    return sync_plans_from_stripe(products)


@not_audited(
    reason="Scheduled system notification job, no actor; its own idempotency "
    "marker is an AuditLog row written directly below for each notice sent, "
    "which is the record that matters here, not a call-level audit entry."
)
def send_trial_ending_notices() -> int:
    """Trial-ending notices (PRD §5 "Scheduled jobs"; docs/plans/phase-5.md
    5.4), daily. Idempotent when run twice: no field on ``Subscription``
    records "already notified" (Phase 1's baseline didn't add one, and
    this phase generates no migrations), so idempotency is checked
    against ``AuditLog`` instead — one row per (subscription, trial end
    date) is the record that a notice already went out for *this* trial
    end. Returns the count of notices actually sent."""
    from keel.audit.models import AuditLog
    from keel.notifications.emails import send_trial_ending_email

    window_end = timezone.now() + timedelta(days=TRIAL_ENDING_NOTICE_WINDOW_DAYS)
    subscriptions = Subscription.objects.filter(
        trial_end__isnull=False, trial_end__lte=window_end, trial_end__gt=timezone.now()
    ).select_related("organization", "organization__created_by")

    sent = 0
    for subscription in subscriptions:
        trial_end = subscription.trial_end
        assert trial_end is not None  # the queryset's trial_end__isnull=False guarantees this
        action = "trial_ending_notice_sent"
        target_id = f"{subscription.pk}:{trial_end.isoformat()}"
        if AuditLog.objects.filter(action=action, target_id=target_id).exists():
            continue
        organization = subscription.organization
        send_trial_ending_email(
            to=organization.created_by.email,
            organization_name=organization.name,
            billing_url=f"{settings.APP_FRONTEND_URL}/{organization.slug}/settings/billing",
            trial_end_date=trial_end.date().isoformat(),
        )
        AuditLog.objects.create(
            organization=organization,
            action=action,
            target_type="Subscription",
            target_id=target_id,
        )
        sent += 1
    return sent


@not_audited(
    reason="Read-only report — nothing here mutates, and 'audited' means "
    "recording a write, not a check. Shared by the rebuild_credit_balances "
    "--check management command and the nightly check_credit_balances_task "
    "beat task (ddia#4), so the comparison is written exactly once."
)
def check_credit_balances(*, organization_id: str | None = None) -> list[dict[str, Any]]:
    """Compares ``CreditBalance`` against a fresh ``SUM`` over
    ``CreditLedgerEntry`` for every organisation (or one, if
    ``organization_id`` is given), locking the balance row before
    aggregating (ddia#3: read skew) so nothing commits in the gap. Never
    writes — report, don't repair (ddia#4): repair is
    ``manage.py rebuild_credit_balances`` with no ``--check`` flag, run by
    an operator on purpose, not by this function or its scheduled
    caller."""
    organizations = Organization.objects.all()
    if organization_id:
        organizations = organizations.filter(id=organization_id)

    drifted: list[dict[str, Any]] = []
    for organization in organizations.iterator():
        with transaction.atomic():
            balance_row, _ = CreditBalance.objects.select_for_update().get_or_create(
                organization=organization
            )
            total = (
                CreditLedgerEntry.objects.filter(organization=organization).aggregate(
                    total=models.Sum("amount")
                )["total"]
                or 0
            )
            if balance_row.balance != total:
                drifted.append(
                    {
                        "organization_id": str(organization.id),
                        "ledger_total": total,
                        "balance": balance_row.balance,
                    }
                )
    return drifted


@not_audited(
    reason="Scheduled system notification job, no actor; same idempotency-marker "
    "reasoning as send_trial_ending_notices above."
)
def check_dunning() -> int:
    """Dunning check (PRD §5 "Scheduled jobs"; docs/plans/phase-5.md 5.4),
    daily. Same idempotency mechanism as ``send_trial_ending_notices``:
    one ``AuditLog`` row per (subscription, current period end) records
    that a payment-failed notice already went out for *this* billing
    period, since ``Subscription`` has no "already notified" field to
    check instead."""
    from keel.audit.models import AuditLog
    from keel.notifications.emails import send_payment_failed_email

    subscriptions = Subscription.objects.filter(status="past_due").select_related(
        "organization", "organization__created_by"
    )

    sent = 0
    for subscription in subscriptions:
        action = "dunning_notice_sent"
        period_marker = (
            subscription.current_period_end.isoformat()
            if subscription.current_period_end
            else "unknown"
        )
        target_id = f"{subscription.pk}:{period_marker}"
        if AuditLog.objects.filter(action=action, target_id=target_id).exists():
            continue
        organization = subscription.organization
        send_payment_failed_email(
            to=organization.created_by.email,
            organization_name=organization.name,
            billing_url=f"{settings.APP_FRONTEND_URL}/{organization.slug}/settings/billing",
        )
        AuditLog.objects.create(
            organization=organization,
            action=action,
            target_type="Subscription",
            target_id=target_id,
        )
        sent += 1
    return sent
