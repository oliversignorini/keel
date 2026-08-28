"""Query-count regression test for ``GET /orgs/<slug>/billing/subscription/``
— the billing overview the client renders on the settings page (Phase
16.A — docs/query-patterns.md)."""

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.billing.models import Plan, Price, Subscription
from keel.organizations import services as org_services

pytestmark = pytest.mark.django_db


def _price() -> Price:
    plan = Plan.objects.create(code="starter", name="Starter", stripe_product_id="prod_starter")
    return Price.objects.create(
        plan=plan,
        stripe_price_id="price_starter_m",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )


def test_get_subscription_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    org = org_services.create_organization(name="Acme", slug="acme", actor=owner)
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_123",
        plan=price.plan,
        price=price,
        status="trialing",
    )

    client = Client()
    client.force_login(owner)

    # 1: session -> session_key. 2: session_key -> User. 3: resolve
    # org_slug -> Organization via active Membership. 4: has_perm's
    # Membership+Role lookup for BILLING_VIEW. 5: the subscription row,
    # select_related("plan") — SubscriptionOut.resolve_plan reads
    # obj.plan.code, which would otherwise be a second query.
    with django_assert_num_queries(5):  # type: ignore[operator]
        response = client.get(f"/api/v1/orgs/{org.slug}/billing/subscription/")
    assert response.status_code == 200
    assert response.json()["subscription"] is not None
