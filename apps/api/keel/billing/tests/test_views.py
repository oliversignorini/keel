"""Checkout, portal, subscription (PRD §7; docs/plans/phase-4.md B.2).
Stripe calls are monkeypatched on ``stripe_client`` — no real Stripe call,
no stripe-mock (PRD §4, "No credentials")."""

import pytest
from rest_framework.test import APIClient

from keel.accounts.models import User
from keel.billing import stripe_client
from keel.billing.models import Plan, Price, Subscription
from keel.organizations import services
from keel.organizations.models import Membership, Organization
from keel.organizations.roles import PRESET_MEMBER, seed_preset_roles

pytestmark = pytest.mark.django_db

_counter = 0


def _user(prefix: str = "user") -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(
        email=f"{prefix}-{_counter}@example.com", password="s3cret-pass"
    )


def _org_with_owner() -> tuple[Organization, User]:
    global _counter
    _counter += 1
    owner = _user("owner")
    org = services.create_organization(name="Acme", slug=f"acme-{_counter}", created_by=owner)
    return org, owner


def _add_member(org: Organization) -> User:
    member = _user("member")
    role = seed_preset_roles()[PRESET_MEMBER]
    Membership.objects.create(
        organization=org, user=member, role=role, status=Membership.STATUS_ACTIVE
    )
    return member


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _price() -> Price:
    plan = Plan.objects.create(code="starter", name="Starter", stripe_product_id="prod_starter")
    return Price.objects.create(
        plan=plan,
        stripe_price_id="price_starter_m",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )


# --- Checkout ---------------------------------------------------------


def test_checkout_returns_url_and_persists_customer_id(monkeypatch: pytest.MonkeyPatch) -> None:
    org, owner = _org_with_owner()
    price = _price()
    monkeypatch.setattr(stripe_client, "create_customer", lambda **kw: "cus_123")
    monkeypatch.setattr(
        stripe_client, "create_checkout_session", lambda **kw: "https://stripe.test/checkout/xyz"
    )

    response = _client_for(owner).post(
        f"/api/v1/organizations/{org.slug}/billing/checkout/", {"price_id": str(price.id)}
    )

    assert response.status_code == 200, response.data
    assert response.data["url"] == "https://stripe.test/checkout/xyz"
    org.refresh_from_db()
    assert org.stripe_customer_id == "cus_123"


def test_checkout_reuses_existing_customer_id(monkeypatch: pytest.MonkeyPatch) -> None:
    org, owner = _org_with_owner()
    org.stripe_customer_id = "cus_existing"
    org.save(update_fields=["stripe_customer_id"])
    price = _price()

    def _fail_create_customer(**kw):
        raise AssertionError("must not create a customer when one already exists")

    monkeypatch.setattr(stripe_client, "create_customer", _fail_create_customer)
    seen = {}

    def _create_checkout_session(**kw):
        seen.update(kw)
        return "https://stripe.test/checkout/xyz"

    monkeypatch.setattr(stripe_client, "create_checkout_session", _create_checkout_session)

    response = _client_for(owner).post(
        f"/api/v1/organizations/{org.slug}/billing/checkout/", {"price_id": str(price.id)}
    )

    assert response.status_code == 200
    assert seen["customer_id"] == "cus_existing"
    assert seen["trial_period_days"] == 14


def test_checkout_requires_billing_manage() -> None:
    org, _owner = _org_with_owner()
    member = _add_member(org)
    price = _price()

    response = _client_for(member).post(
        f"/api/v1/organizations/{org.slug}/billing/checkout/", {"price_id": str(price.id)}
    )

    assert response.status_code == 403
    assert response.data["error"]["code"] == "insufficient_role"


def test_checkout_rejects_inactive_price() -> None:
    org, owner = _org_with_owner()
    price = _price()
    price.is_active = False
    price.save(update_fields=["is_active"])

    response = _client_for(owner).post(
        f"/api/v1/organizations/{org.slug}/billing/checkout/", {"price_id": str(price.id)}
    )

    assert response.status_code == 422
    assert response.data["error"]["code"] == "price_not_found"


def test_checkout_blocks_a_downgrade_below_current_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """docs/plans/phase-4.md B.4: plan downgrade below current usage is
    blocked, naming what's over — and no Stripe call is made."""
    from keel.billing import entitlements

    org, owner = _org_with_owner()
    old_plan = Plan.objects.create(code="pro", name="Pro", stripe_product_id="prod_pro_dg")
    old_price = Price.objects.create(
        plan=old_plan,
        stripe_price_id="price_pro_dg",
        interval=Price.INTERVAL_MONTH,
        unit_amount=4900,
        currency="AUD",
    )
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_pro_dg",
        plan=old_plan,
        price=old_price,
        status="active",
    )
    new_plan = Plan.objects.create(
        code="starter-dg",
        name="Starter",
        stripe_product_id="prod_starter_dg",
        entitlements={"limits": {"seats": 1}},
    )
    new_price = Price.objects.create(
        plan=new_plan,
        stripe_price_id="price_starter_dg",
        interval=Price.INTERVAL_MONTH,
        unit_amount=900,
        currency="AUD",
    )
    monkeypatch.setitem(entitlements._resource_counters, "seats", lambda organization: 3)

    def _fail(**kw):
        raise AssertionError("must not call Stripe when the downgrade is blocked")

    monkeypatch.setattr(stripe_client, "create_checkout_session", _fail)

    response = _client_for(owner).post(
        f"/api/v1/organizations/{org.slug}/billing/checkout/", {"price_id": str(new_price.id)}
    )

    assert response.status_code == 409, response.data
    assert response.data["error"]["code"] == "downgrade_blocked"
    assert "seats" in response.data["error"]["message"]


def test_checkout_404s_for_nonmember() -> None:
    org, _owner = _org_with_owner()
    outsider = _user("outsider")
    price = _price()

    response = _client_for(outsider).post(
        f"/api/v1/organizations/{org.slug}/billing/checkout/", {"price_id": str(price.id)}
    )

    assert response.status_code == 404


# --- Portal -------------------------------------------------------------


def test_portal_returns_url(monkeypatch: pytest.MonkeyPatch) -> None:
    org, owner = _org_with_owner()
    org.stripe_customer_id = "cus_existing"
    org.save(update_fields=["stripe_customer_id"])
    monkeypatch.setattr(
        stripe_client,
        "create_billing_portal_session",
        lambda **kw: "https://stripe.test/portal/xyz",
    )

    response = _client_for(owner).post(f"/api/v1/organizations/{org.slug}/billing/portal/")

    assert response.status_code == 200
    assert response.data["url"] == "https://stripe.test/portal/xyz"


def test_portal_requires_billing_manage() -> None:
    org, _owner = _org_with_owner()
    member = _add_member(org)

    response = _client_for(member).post(f"/api/v1/organizations/{org.slug}/billing/portal/")

    assert response.status_code == 403


# --- Subscription ---------------------------------------------------------


def test_subscription_returns_null_when_none_exists() -> None:
    org, owner = _org_with_owner()

    response = _client_for(owner).get(f"/api/v1/organizations/{org.slug}/billing/subscription/")

    assert response.status_code == 200
    assert response.data["subscription"] is None


def test_subscription_returns_row_when_one_exists() -> None:
    org, owner = _org_with_owner()
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_123",
        plan=price.plan,
        price=price,
        status="trialing",
    )

    response = _client_for(owner).get(f"/api/v1/organizations/{org.slug}/billing/subscription/")

    assert response.status_code == 200
    assert response.data["subscription"]["status"] == "trialing"
    assert response.data["subscription"]["plan"] == "starter"


def test_subscription_view_is_readable_by_billing_view_alone() -> None:
    org, _owner = _org_with_owner()
    member = _add_member(org)

    response = _client_for(member).get(f"/api/v1/organizations/{org.slug}/billing/subscription/")

    assert response.status_code == 200


def test_subscription_404s_for_nonmember() -> None:
    org, _owner = _org_with_owner()
    outsider = _user("outsider")

    response = _client_for(outsider).get(f"/api/v1/organizations/{org.slug}/billing/subscription/")

    assert response.status_code == 404
