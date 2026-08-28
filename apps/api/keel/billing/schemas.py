"""Billing schemas (PRD §7; docs/plans/phase-4.md B.1; phase-10.md 10.C)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field

from keel.billing.models import Price
from keel.core.schemas import KeelSchema

# api-patterns finding 14: a published vocabulary, not a bare `str` — must
# match Price.INTERVAL_CHOICES (keel/billing/models.py).
PriceInterval = Literal["month", "year"]
assert set(PriceInterval.__args__) == {choice for choice, _ in Price.INTERVAL_CHOICES}  # type: ignore[attr-defined]

# Subscription.status has no model-level choices (keel/billing/models.py) —
# Stripe, not this table, is the source of truth for a subscription's
# status vocabulary (https://docs.stripe.com/api/subscriptions/object,
# `status`). Published here so the generated client gets an enum instead
# of `str`; keep in step with Stripe's own set if it ever changes.
SubscriptionStatus = Literal[
    "incomplete",
    "incomplete_expired",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
    "paused",
]


class PriceOut(KeelSchema):
    interval: PriceInterval
    unit_amount: int
    currency: str


class EntitlementsOut(Schema):
    """Replaces the ``dict[str, Any]`` blob (api-patterns finding 15) —
    the shape ``keel.billing.entitlements.resolve_entitlements`` already
    documents and ``keel.billing.models.EntitlementsSpec`` now validates
    on ``Plan.save()``. Published here so the generated client gets real
    fields instead of an opaque map it can't type-check a gate against."""

    features: list[str] = Field(default_factory=list)
    limits: dict[str, int | None] = Field(default_factory=dict)


class PlanOut(KeelSchema):
    code: str
    name: str
    entitlements: EntitlementsOut
    sort_order: int
    prices: list[PriceOut]

    @staticmethod
    def resolve_prices(obj: Any) -> list[Any]:
        # ``get_queryset`` prefetches only active prices into this
        # attribute — public callers never see a price Stripe has
        # deactivated (docs/plans/phase-4.md B.1).
        return getattr(obj, "active_prices", [])


class SubscriptionOut(KeelSchema):
    plan: str
    status: SubscriptionStatus
    quantity: int
    current_period_end: datetime | None
    trial_end: datetime | None
    cancel_at_period_end: bool

    @staticmethod
    def resolve_plan(obj: Any) -> str:
        return str(obj.plan.code)


class CheckoutIn(Schema):
    price_id: UUID


# --- Response shapes for the routes that used to return a bare dict -------
# (api-patterns finding 4: the generated client typed each of these `void`.)


class CheckoutSessionOut(Schema):
    url: str


class BillingPortalOut(Schema):
    url: str


class SubscriptionEnvelopeOut(Schema):
    subscription: SubscriptionOut | None


class CreditBalanceOut(Schema):
    balance: int
