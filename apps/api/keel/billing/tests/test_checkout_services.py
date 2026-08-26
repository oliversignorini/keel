"""``ensure_stripe_customer`` / ``create_checkout_session`` /
``create_portal_session`` (docs/plans/phase-4.md B.2). Stripe calls are
monkeypatched — no real Stripe call, no stripe-mock (PRD §4, "No
credentials"). Also proves PRD §4 invariant 3: no Stripe call happens
inside an open transaction.
"""

import pytest
from django.db import connection

from keel.accounts.models import User
from keel.billing import services, stripe_client
from keel.billing.models import Plan, Price
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


def _org() -> Organization:
    creator = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    return Organization.objects.create(name="Acme", slug="acme", created_by=creator)


def _price() -> Price:
    plan = Plan.objects.create(code="starter", name="Starter", stripe_product_id="prod_starter")
    return Price.objects.create(
        plan=plan,
        stripe_price_id="price_starter_m",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )


def test_ensure_stripe_customer_creates_and_persists_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org = _org()
    calls = []

    def fake_create_customer(**kw):
        calls.append(kw)
        return "cus_new"

    monkeypatch.setattr(stripe_client, "create_customer", fake_create_customer)

    first = services.ensure_stripe_customer(org)
    second = services.ensure_stripe_customer(org)

    assert first == "cus_new"
    assert second == "cus_new"
    assert len(calls) == 1, "the second call must reuse the persisted id, not hit Stripe again"
    org.refresh_from_db()
    assert org.stripe_customer_id == "cus_new"


def test_stripe_call_does_not_open_its_own_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """PRD §4 invariant 3: "no Stripe call happens inside an open
    transaction". pytest-django wraps every test in an outer transaction
    for rollback, so what's actually checkable here is that the service
    itself doesn't wrap the Stripe call in its *own* nested atomic() /
    savepoint — if it did, `connection.savepoint_ids` would be longer
    inside the fake than it is at the call site, same shape as
    ``keel/organizations/services.py``'s "atomic opened here, never in a
    view" discipline applied to Stripe instead."""
    org = _org()
    price = _price()
    baseline_depth = len(connection.savepoint_ids)
    observed_depths = []

    def fake_create_customer(**kw):
        observed_depths.append(len(connection.savepoint_ids))
        return "cus_new"

    def fake_create_checkout_session(**kw):
        observed_depths.append(len(connection.savepoint_ids))
        return "https://stripe.test/checkout/xyz"

    monkeypatch.setattr(stripe_client, "create_customer", fake_create_customer)
    monkeypatch.setattr(stripe_client, "create_checkout_session", fake_create_checkout_session)

    services.create_checkout_session(
        organization=org,
        actor=org.created_by,
        price=price,
        success_url="https://app.test/success",
        cancel_url="https://app.test/cancel",
    )

    assert observed_depths == [baseline_depth, baseline_depth]


def test_create_portal_session_reuses_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    org = _org()
    org.stripe_customer_id = "cus_existing"
    org.save(update_fields=["stripe_customer_id"])
    seen = {}

    def fake_portal(**kw):
        seen.update(kw)
        return "https://stripe.test/portal/xyz"

    monkeypatch.setattr(stripe_client, "create_billing_portal_session", fake_portal)

    url = services.create_portal_session(
        organization=org, actor=org.created_by, return_url="https://app.test/billing"
    )

    assert url == "https://stripe.test/portal/xyz"
    assert seen == {"customer_id": "cus_existing", "return_url": "https://app.test/billing"}
