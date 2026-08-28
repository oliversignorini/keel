"""``GET /api/v1/plans/`` (PRD §7) — public, cursor-paginated, lists only
active plans and their active prices.

Cursor-paginated like every other collection — see
``keel/billing/views.py``'s module docstring for why
``(sort_order, code)`` is a valid ordering for ``CursorPaginator``.
"""

import pytest
from django.test import Client

from keel.billing.models import Plan, Price
from keel.billing.views import PlanResource
from keel.organizations.tests.ninja_tenant_isolation import iter_global_justifications

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

    response = Client().get("/api/v1/plans/")

    assert response.status_code == 200


def test_list_plans_returns_active_plans_with_nested_active_prices() -> None:
    plan = _plan("starter")
    active_price = _price(plan, "price_active")
    _price(plan, "price_inactive", is_active=False)
    _plan("legacy", is_active=False)

    response = Client().get("/api/v1/plans/")

    results = response.json()["results"]
    codes = [row["code"] for row in results]
    assert codes == ["starter"]

    prices = results[0]["prices"]
    assert [row["id"] for row in prices] == [str(active_price.id)]


def test_list_plans_is_cursor_paginated() -> None:
    """The bare-array deviation from PRD §7's "all collections are
    cursor-paginated" convention is fixed here, not carried over."""
    _plan("starter")

    response = Client().get("/api/v1/plans/")

    body = response.json()
    assert set(body.keys()) == {"results", "next", "previous"}
    assert isinstance(body["results"], list)


def test_list_plans_orders_by_sort_order_then_code() -> None:
    _plan("gold", sort_order=1)
    _plan("bronze", sort_order=0)

    response = Client().get("/api/v1/plans/")

    codes = [row["code"] for row in response.json()["results"]]
    assert codes == ["bronze", "gold"]


def test_plan_serializer_exposes_entitlements() -> None:
    plan = _plan("starter")
    plan.entitlements = {"features": ["api_access"], "limits": {"seats": 5}}
    plan.save()

    response = Client().get("/api/v1/plans/")

    assert response.json()["results"][0]["entitlements"] == {
        "features": ["api_access"],
        "limits": {"seats": 5},
    }


def test_list_plans_sets_cache_control_and_etag() -> None:
    """api-patterns finding 13: /plans/ is a Reference Data Holder —
    unauthenticated, long-lived, read by every pricing-page visit."""
    _plan("starter")

    response = Client().get("/api/v1/plans/")

    assert response["Cache-Control"] == "public, max-age=300"
    assert response["ETag"]


def test_plan_resource_declares_a_real_global_justification() -> None:
    assert PlanResource.organization_scoped is False
    justification = PlanResource.GLOBAL_JUSTIFICATION
    assert justification
    assert len(justification) > 40, "GLOBAL_JUSTIFICATION reads like a placeholder, not a reason"


def test_plan_resource_justification_is_printed_regardless_of_router() -> None:
    """``PlanResource`` is registered on its own public router, not any
    router at all in the DRF-router sense — the justification print
    must find it anyway, because it walks the ``GlobalResource``
    registry (PRD §4 invariant 7)."""
    justifications = list(iter_global_justifications())

    assert ("PlanResource", PlanResource.GLOBAL_JUSTIFICATION) in justifications
