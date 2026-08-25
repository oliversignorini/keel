"""Billing serializers (PRD §7; docs/plans/phase-4.md B.1)."""

from typing import Any

from rest_framework import serializers

from keel.billing.models import Plan, Price, Subscription


class PriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Price
        fields = ("id", "interval", "unit_amount", "currency")


class PlanSerializer(serializers.ModelSerializer):
    prices = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = ("id", "code", "name", "entitlements", "sort_order", "prices")

    def get_prices(self, plan: Plan) -> list[dict[str, Any]]:
        # ``get_queryset`` prefetches only active prices into this
        # attribute — public callers never see a price Stripe has
        # deactivated (docs/plans/phase-4.md B.1).
        active_prices: list[Price] = getattr(plan, "active_prices", [])
        data: list[dict[str, Any]] = PriceSerializer(active_prices, many=True).data
        return data


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = serializers.CharField(source="plan.code", read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id",
            "plan",
            "status",
            "quantity",
            "current_period_end",
            "trial_end",
            "cancel_at_period_end",
        )


class CheckoutRequestSerializer(serializers.Serializer):
    price_id = serializers.UUIDField()
