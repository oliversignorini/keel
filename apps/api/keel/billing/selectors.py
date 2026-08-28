"""Reads (PRD §4 invariant 1). Services mutate and return; this module
queries and returns. Nothing here writes."""

from datetime import datetime, timedelta
from uuid import UUID

from django.db.models import Max, Prefetch, QuerySet
from django.utils import timezone

from keel.billing.models import Plan, Price, StripeEvent, Subscription
from keel.organizations.models import Organization

STALE_EVENT_THRESHOLD = timedelta(minutes=5)


def list_active_plans() -> QuerySet[Plan]:
    active_prices = Prefetch(
        "prices",
        queryset=Price.objects.filter(is_active=True).order_by("interval"),
        to_attr="active_prices",
    )
    return (
        Plan.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .prefetch_related(active_prices)
    )


def latest_catalogue_update() -> tuple[datetime | None, datetime | None]:
    """The two timestamps ``GET /plans/``'s ETag is built from (api-patterns
    finding 13, Reference Data Holder) — a plan change and a price change
    are tracked separately since a price change doesn't touch
    ``Plan.updated_at``."""
    plan_latest = Plan.objects.filter(is_active=True).aggregate(latest=Max("updated_at"))["latest"]
    price_latest = Price.objects.filter(is_active=True).aggregate(latest=Max("updated_at"))[
        "latest"
    ]
    return plan_latest, price_latest


def get_active_price(price_id: str | UUID) -> Price | None:
    return Price.objects.filter(pk=str(price_id), is_active=True).first()


def get_subscription(organization: Organization) -> Subscription | None:
    """``SubscriptionOut.resolve_plan`` reads ``obj.plan.code`` — without
    ``select_related("plan")`` that is a second query on every call."""
    return Subscription.objects.filter(organization=organization).select_related("plan").first()


def stale_unprocessed_stripe_event_ids() -> list[str]:
    """Ids of every ``StripeEvent`` still unprocessed
    ``STALE_EVENT_THRESHOLD`` after receipt — what the beat sweeper
    (``keel.billing.tasks.sweep_unprocessed_stripe_events``) re-dispatches.
    A read, so it lives here rather than in ``services.py``; the sweeper
    task owns the enqueue direction."""
    threshold = timezone.now() - STALE_EVENT_THRESHOLD
    return list(
        StripeEvent.objects.filter(
            processed_at__isnull=True, received_at__lt=threshold
        ).values_list("pk", flat=True)
    )
