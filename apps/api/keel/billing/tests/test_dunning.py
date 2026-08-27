"""Dunning (docs/plans/phase-4.md B.6): ``invoice.payment_failed`` puts the
organisation into a dunning state (``Subscription.status = "past_due"``,
which ``GET .../billing/subscription/`` surfaces for the frontend banner
— PRD §7). Access is deliberately **not** revoked: entitlements resolve
identically for an active and a past-due subscription. The webhook
transition itself (invoice.payment_failed -> past_due, invoice.paid ->
active) is tested end-to-end in ``test_webhooks_replay.py``; this module
covers the "access is not immediately revoked" half specifically."""

import pytest
from django.test import Client as APIClient

from keel.accounts.models import User
from keel.billing.entitlements import check_feature, check_limit, resolve_entitlements
from keel.billing.models import Plan, Price, Subscription
from keel.core.exceptions import PaymentRequired
from keel.organizations import services
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db

_counter = 0


def _org_with_owner() -> tuple[Organization, User]:
    global _counter
    _counter += 1
    owner = User.objects.create_user(
        email=f"owner-dun-{_counter}@example.com", password="s3cret-pass"
    )
    org = services.create_organization(name="Acme", slug=f"acme-dun-{_counter}", created_by=owner)
    return org, owner


def _subscribe(org: Organization, status: str) -> Subscription:
    plan = Plan.objects.create(
        code=f"plan-dun-{org.pk}",
        name="Plan",
        stripe_product_id=f"prod-dun-{org.pk}",
        entitlements={"features": ["api_access"], "limits": {"seats": 5}},
    )
    price = Price.objects.create(
        plan=plan,
        stripe_price_id=f"price-dun-{org.pk}",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )
    return Subscription.objects.create(
        organization=org,
        stripe_subscription_id=f"sub-dun-{org.pk}",
        plan=plan,
        price=price,
        status=status,
    )


def test_past_due_subscription_keeps_full_entitlements() -> None:
    org, _owner = _org_with_owner()
    _subscribe(org, status="past_due")

    check_feature(org, "api_access")  # does not raise
    check_limit(org, "seats")  # does not raise
    assert resolve_entitlements(org) == {"features": ["api_access"], "limits": {"seats": 5}}


def test_past_due_and_active_resolve_identical_entitlements() -> None:
    org_active, _owner_a = _org_with_owner()
    org_past_due, _owner_b = _org_with_owner()
    _subscribe(org_active, status="active")
    # Give both the same plan by copying entitlements rather than sharing
    # a Plan row, so the two organisations stay independent.
    plan_active = Subscription.objects.get(organization=org_active).plan
    price_past_due = Price.objects.create(
        plan=plan_active,
        stripe_price_id=f"price-dun-shared-{org_past_due.pk}",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )
    Subscription.objects.create(
        organization=org_past_due,
        stripe_subscription_id=f"sub-dun-shared-{org_past_due.pk}",
        plan=plan_active,
        price=price_past_due,
        status="past_due",
    )

    assert resolve_entitlements(org_active) == resolve_entitlements(org_past_due)


def test_dunning_state_is_visible_but_does_not_gate_the_subscription_endpoint() -> None:
    """The banner reads status from GET .../billing/subscription/ (PRD
    §7) — confirming the dunning state is visible, not confirming banner
    UI, which is p4-billing-web's job."""
    org, owner = _org_with_owner()
    _subscribe(org, status="past_due")
    client = APIClient()
    client.force_login(owner)

    response = client.get(f"/api/v1/orgs/{org.slug}/billing/subscription/")

    assert response.status_code == 200
    assert response.json()["subscription"]["status"] == "past_due"


def test_seat_beyond_limit_still_denied_regardless_of_dunning() -> None:
    """Dunning relaxes nothing about entitlement limits themselves — a
    past-due org over its seat cap is still denied, exactly as an active
    one would be. B.6 only guarantees access isn't revoked *because of*
    dunning, not that limits stop applying."""
    org, _owner = _org_with_owner()
    subscription = _subscribe(org, status="past_due")
    subscription.plan.entitlements = {"limits": {"seats": 0}}
    subscription.plan.save(update_fields=["entitlements"])

    with pytest.raises(PaymentRequired):
        check_limit(org, "seats")
