"""Every handled Stripe webhook event type, replayed twice through the
real endpoint — "deliver the webhook twice the way Stripe would"
(docs/plans/phase-4.md B.3), not just calling a handler function twice in
one transaction. Signatures are generated locally via
``stripe.WebhookSignature`` — no real Stripe call, no stripe-mock.
No coverage exemption for this module (PRD §7 coverage table).
"""

import json

import pytest
import stripe
from rest_framework.test import APIClient

from keel.accounts.models import User
from keel.billing.models import Plan, Price, StripeEvent, Subscription
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "whsec_test_fixture_secret"


@pytest.fixture(autouse=True)
def _webhook_secret(settings):
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET


def _post_signed(event: dict, client: APIClient | None = None):
    client = client or APIClient()
    body = json.dumps(event).encode()
    header = stripe.WebhookSignature.generate_signature_header(
        payload=body.decode(), secret=WEBHOOK_SECRET
    )
    return client.post(
        "/api/v1/stripe/webhook/",
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
    )


def _org(customer_id: str = "cus_replay") -> Organization:
    creator = User.objects.create_user(email="owner-replay@example.com", password="s3cret-pass")
    return Organization.objects.create(
        name="Acme", slug="acme-replay", created_by=creator, stripe_customer_id=customer_id
    )


def _price(stripe_price_id: str = "price_replay") -> Price:
    plan = Plan.objects.create(code="starter", name="Starter", stripe_product_id="prod_replay")
    return Price.objects.create(
        plan=plan,
        stripe_price_id=stripe_price_id,
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )


def _subscription_object(
    subscription_id: str, customer_id: str, price_id: str, status: str
) -> dict:
    return {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "items": {"data": [{"price": {"id": price_id}, "quantity": 1}]},
        "current_period_end": 1_700_000_000,
        "trial_end": None,
        "cancel_at_period_end": False,
    }


def _subscription_snapshot() -> dict | None:
    row = Subscription.objects.first()
    if row is None:
        return None
    return {
        "stripe_subscription_id": row.stripe_subscription_id,
        "plan_id": str(row.plan_id),
        "price_id": str(row.price_id),
        "status": row.status,
        "quantity": row.quantity,
        "current_period_end": row.current_period_end,
        "cancel_at_period_end": row.cancel_at_period_end,
    }


def _assert_identical_after_replay(event: dict) -> None:
    client = APIClient()
    first = _post_signed(event, client)
    assert first.status_code == 200, first.data
    before = _subscription_snapshot()
    row_count_after_first = Subscription.objects.count()

    second = _post_signed(event, client)

    assert second.status_code == 200, second.data
    assert Subscription.objects.count() == row_count_after_first
    assert _subscription_snapshot() == before
    assert StripeEvent.objects.get(pk=event["id"]).error == ""
    assert StripeEvent.objects.get(pk=event["id"]).processed_at is not None


def test_checkout_session_completed_replayed_twice() -> None:
    _org()
    event = {
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_1", "customer": "cus_replay"}},
    }

    _assert_identical_after_replay(event)

    assert not Subscription.objects.exists()


def test_customer_subscription_created_replayed_twice() -> None:
    _org()
    price = _price()
    event = {
        "id": "evt_sub_created",
        "type": "customer.subscription.created",
        "data": {
            "object": _subscription_object("sub_1", "cus_replay", price.stripe_price_id, "active")
        },
    }

    _assert_identical_after_replay(event)

    subscription = Subscription.objects.get()
    assert subscription.status == "active"
    assert subscription.stripe_subscription_id == "sub_1"


def test_customer_subscription_updated_replayed_twice() -> None:
    org = _org()
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_1",
        plan=price.plan,
        price=price,
        status="trialing",
    )
    event = {
        "id": "evt_sub_updated",
        "type": "customer.subscription.updated",
        "data": {
            "object": _subscription_object("sub_1", "cus_replay", price.stripe_price_id, "active")
        },
    }

    _assert_identical_after_replay(event)

    assert Subscription.objects.get().status == "active"


def test_customer_subscription_deleted_replayed_twice() -> None:
    org = _org()
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_1",
        plan=price.plan,
        price=price,
        status="active",
    )
    event = {
        "id": "evt_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": _subscription_object("sub_1", "cus_replay", price.stripe_price_id, "canceled")
        },
    }

    _assert_identical_after_replay(event)

    assert Subscription.objects.get().status == "canceled"


def test_invoice_paid_replayed_twice() -> None:
    org = _org()
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_1",
        plan=price.plan,
        price=price,
        status="past_due",
    )
    event = {
        "id": "evt_invoice_paid",
        "type": "invoice.paid",
        "data": {"object": {"id": "in_1", "customer": "cus_replay"}},
    }

    _assert_identical_after_replay(event)

    assert Subscription.objects.get().status == "active"


def test_invoice_payment_failed_replayed_twice() -> None:
    org = _org()
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_1",
        plan=price.plan,
        price=price,
        status="active",
    )
    event = {
        "id": "evt_invoice_failed",
        "type": "invoice.payment_failed",
        "data": {"object": {"id": "in_1", "customer": "cus_replay"}},
    }

    _assert_identical_after_replay(event)

    assert Subscription.objects.get().status == "past_due"
