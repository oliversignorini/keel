"""``GET /api/v1/plans/`` (PRD §7; docs/plans/phase-4.md B.1) — public,
lists only active plans and their active prices."""

import pytest
from rest_framework.test import APIClient

from keel.billing.models import Plan, Price
from keel.billing.viewsets import PlanViewSet
from keel.organizations.tests.tenant_isolation import iter_global_justifications

pytestmark = pytest.mark.django_db


def _plan(code: str, is_active: bool = True, sort_order: int = 0) -> Plan:
    return Plan.objects.create(
        code=code,
        name=code.title(),
        stripe_product_id=f"prod_{code}",
        is_active=is_active,
        sort_order=sort_order,
    )


def _price(plan: Plan, stripe_price_id: str, is_active: bool = True) -> Price:
    return Price.objects.create(
        plan=plan,
        stripe_price_id=stripe_price_id,
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
        is_active=is_active,
    )


def test_list_plans_is_public() -> None:
    _plan("starter")

    response = APIClient().get("/api/v1/plans/")

    assert response.status_code == 200


def test_list_plans_returns_active_plans_with_nested_active_prices() -> None:
    plan = _plan("starter")
    active_price = _price(plan, "price_active")
    _price(plan, "price_inactive", is_active=False)
    _plan("legacy", is_active=False)

    response = APIClient().get("/api/v1/plans/")

    codes = [row["code"] for row in response.data["results"]]
    assert codes == ["starter"]

    prices = response.data["results"][0]["prices"]
    assert [row["id"] for row in prices] == [str(active_price.id)]


def test_list_plans_orders_by_sort_order_then_code() -> None:
    _plan("gold", sort_order=1)
    _plan("bronze", sort_order=0)

    response = APIClient().get("/api/v1/plans/")

    codes = [row["code"] for row in response.data["results"]]
    assert codes == ["bronze", "gold"]


def test_plan_serializer_exposes_entitlements() -> None:
    plan = _plan("starter")
    plan.entitlements = {"seats": 5, "features": ["api_access"]}
    plan.save()

    response = APIClient().get("/api/v1/plans/")

    assert response.data["results"][0]["entitlements"] == {
        "seats": 5,
        "features": ["api_access"],
    }


def test_plan_viewset_declares_a_real_global_justification() -> None:
    assert PlanViewSet.organization_scoped is False
    justification = PlanViewSet.GLOBAL_JUSTIFICATION
    assert justification
    assert len(justification) > 40, "GLOBAL_JUSTIFICATION reads like a placeholder, not a reason"


def test_plan_viewset_justification_is_printable_by_the_router_walk() -> None:
    from rest_framework.routers import SimpleRouter

    router = SimpleRouter()
    router.register("plans", PlanViewSet, basename="fixture-plan")

    justifications = list(iter_global_justifications(router))

    assert justifications == [("PlanViewSet", PlanViewSet.GLOBAL_JUSTIFICATION)]
