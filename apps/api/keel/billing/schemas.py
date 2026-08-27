"""Billing schemas (PRD §7; docs/plans/phase-4.md B.1; phase-10.md 10.C)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from ninja import Schema


class PriceOut(Schema):
    id: str
    interval: str
    unit_amount: int
    currency: str

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)


class PlanOut(Schema):
    id: str
    code: str
    name: str
    entitlements: dict[str, Any]
    sort_order: int
    prices: list[PriceOut]

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

    @staticmethod
    def resolve_prices(obj: Any) -> list[Any]:
        # ``get_queryset`` prefetches only active prices into this
        # attribute — public callers never see a price Stripe has
        # deactivated (docs/plans/phase-4.md B.1).
        return getattr(obj, "active_prices", [])


class SubscriptionOut(Schema):
    id: str
    plan: str
    status: str
    quantity: int
    current_period_end: datetime | None
    trial_end: datetime | None
    cancel_at_period_end: bool

    @staticmethod
    def resolve_id(obj: Any) -> str:
        return str(obj.id)

    @staticmethod
    def resolve_plan(obj: Any) -> str:
        return str(obj.plan.code)


class CheckoutIn(Schema):
    price_id: UUID
