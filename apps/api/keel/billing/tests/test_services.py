"""``sync_plans_from_stripe`` (docs/plans/phase-4.md B.1) — pure logic over
recorded fixture dicts shaped like ``stripe_client.fetch_products_and_prices``
returns. No real Stripe call, no stripe-mock: PRD §4 "No credentials.
stripe-mock or recorded fixtures throughout.\""""

import pytest

from keel.billing.models import Plan, Price
from keel.billing.services import MissingPlanCode, sync_plans_from_stripe

pytestmark = pytest.mark.django_db


def _product(
    product_id: str = "prod_starter",
    code: str = "starter",
    name: str = "Starter",
    price_id: str = "price_starter_monthly",
    unit_amount: int = 1900,
    interval: str = "month",
    currency: str = "aud",
) -> dict:
    return {
        "id": product_id,
        "name": name,
        "metadata": {"code": code},
        "prices": [
            {
                "id": price_id,
                "unit_amount": unit_amount,
                "currency": currency,
                "recurring": {"interval": interval},
            }
        ],
    }


def test_sync_creates_plan_and_price() -> None:
    result = sync_plans_from_stripe([_product()])

    plan = Plan.objects.get(stripe_product_id="prod_starter")
    assert plan.code == "starter"
    assert plan.name == "Starter"
    assert plan.is_active is True

    price = Price.objects.get(stripe_price_id="price_starter_monthly")
    assert price.plan == plan
    assert price.unit_amount == 1900
    assert price.currency == "AUD"
    assert price.interval == Price.INTERVAL_MONTH

    assert result == {
        "plans_synced": 1,
        "prices_synced": 1,
        "plans_deactivated": 0,
        "prices_deactivated": 0,
    }


def test_sync_is_idempotent() -> None:
    sync_plans_from_stripe([_product()])
    sync_plans_from_stripe([_product()])

    assert Plan.objects.count() == 1
    assert Price.objects.count() == 1


def test_sync_updates_existing_plan_and_price_in_place() -> None:
    sync_plans_from_stripe([_product(name="Starter")])

    sync_plans_from_stripe([_product(name="Starter (renamed)", unit_amount=2900)])

    plan = Plan.objects.get(stripe_product_id="prod_starter")
    assert plan.name == "Starter (renamed)"
    price = Price.objects.get(stripe_price_id="price_starter_monthly")
    assert price.unit_amount == 2900
    assert Plan.objects.count() == 1
    assert Price.objects.count() == 1


def test_sync_deactivates_plan_no_longer_returned_by_stripe() -> None:
    sync_plans_from_stripe([_product()])

    sync_plans_from_stripe([])

    plan = Plan.objects.get(stripe_product_id="prod_starter")
    assert plan.is_active is False
    price = Price.objects.get(stripe_price_id="price_starter_monthly")
    assert price.is_active is False


def test_sync_reactivates_a_previously_deactivated_plan() -> None:
    sync_plans_from_stripe([_product()])
    sync_plans_from_stripe([])

    sync_plans_from_stripe([_product()])

    plan = Plan.objects.get(stripe_product_id="prod_starter")
    assert plan.is_active is True


def test_sync_handles_multiple_products_and_prices() -> None:
    starter = _product(product_id="prod_starter", code="starter", price_id="price_starter_m")
    starter["prices"].append(
        {
            "id": "price_starter_y",
            "unit_amount": 19000,
            "currency": "aud",
            "recurring": {"interval": "year"},
        }
    )
    pro = _product(
        product_id="prod_pro", code="pro", name="Pro", price_id="price_pro_m", unit_amount=4900
    )

    result = sync_plans_from_stripe([starter, pro])

    assert result["plans_synced"] == 2
    assert result["prices_synced"] == 3
    assert Plan.objects.filter(code="starter").exists()
    assert Plan.objects.filter(code="pro").exists()
    assert Price.objects.get(stripe_price_id="price_starter_y").interval == Price.INTERVAL_YEAR


def test_sync_raises_missing_plan_code_for_a_product_with_no_code_metadata() -> None:
    product = _product()
    product["metadata"] = {}

    with pytest.raises(MissingPlanCode):
        sync_plans_from_stripe([product])

    assert not Plan.objects.exists(), "the whole sync must roll back, not partially apply"
