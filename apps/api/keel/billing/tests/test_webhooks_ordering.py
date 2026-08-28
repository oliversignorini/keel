"""Webhook LWW ordering guard and invoice.paid's narrowed transition:
Stripe guarantees neither delivery order nor at-most-once
delivery, so handlers called directly here simulate what an out-of-order
redelivery looks like — the same shape ``test_webhooks_posthog.py`` uses,
not a real HTTP round trip (that's ``test_webhooks_replay.py``'s job)."""

import pytest

from keel.accounts.models import User
from keel.billing import webhooks
from keel.billing.models import Plan, Price, Subscription
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db

EARLY = 1_700_000_000
LATE = 1_700_000_500


def _org(customer_id: str = "cus_order") -> Organization:
    creator = User.objects.create_user(email="owner-order@example.com", password="s3cret-pass")
    return Organization.objects.create(
        name="Acme", slug="acme-order", created_by=creator, stripe_customer_id=customer_id
    )


def _price() -> Price:
    plan = Plan.objects.create(code="starter", name="Starter", stripe_product_id="prod_order")
    return Price.objects.create(
        plan=plan,
        stripe_price_id="price_order",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )


def _subscription_object(status: str) -> dict:
    price = Price.objects.get(stripe_price_id="price_order")
    return {
        "id": "sub_order",
        "customer": "cus_order",
        "status": status,
        "items": {"data": [{"price": {"id": price.stripe_price_id}, "quantity": 1}]},
        "current_period_end": None,
        "trial_end": None,
        "cancel_at_period_end": False,
    }


def test_an_out_of_order_subscription_event_does_not_overwrite_a_newer_one() -> None:
    """`customer.subscription.deleted` (newer) then a late-delivered
    `customer.subscription.updated` (older) must not resurrect the
    cancelled subscription."""
    _org()
    _price()

    webhooks._handle_subscription_event(_subscription_object("canceled"), LATE)
    webhooks._handle_subscription_event(_subscription_object("active"), EARLY)

    assert Subscription.objects.get().status == "canceled"


def test_a_newer_subscription_event_still_applies_after_an_older_one() -> None:
    _org()
    _price()

    webhooks._handle_subscription_event(_subscription_object("trialing"), EARLY)
    webhooks._handle_subscription_event(_subscription_object("active"), LATE)

    subscription = Subscription.objects.get()
    assert subscription.status == "active"
    assert subscription.stripe_updated_at is not None


def test_subscription_events_with_no_event_created_timestamp_still_apply_in_delivery_order() -> (
    None
):
    """A hand-built payload (or any Stripe event genuinely missing
    `created`) must not be silently dropped by the guard — the guard is a
    no-op when there's nothing to compare."""
    _org()
    _price()

    webhooks._handle_subscription_event(_subscription_object("trialing"), None)
    webhooks._handle_subscription_event(_subscription_object("active"), None)

    assert Subscription.objects.get().status == "active"


def test_invoice_paid_only_transitions_past_due_to_active() -> None:
    org = _org()
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_order",
        plan=price.plan,
        price=price,
        status="canceled",
    )

    webhooks._handle_invoice_paid({"customer": "cus_order"}, LATE)

    assert Subscription.objects.get().status == "canceled"


def test_invoice_paid_does_transition_past_due_to_active() -> None:
    org = _org()
    price = _price()
    Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_order",
        plan=price.plan,
        price=price,
        status="past_due",
    )

    webhooks._handle_invoice_paid({"customer": "cus_order"}, LATE)

    assert Subscription.objects.get().status == "active"


def _existing_subscription(org: Organization, price: Price, status: str) -> Subscription:
    return Subscription.objects.create(
        organization=org,
        stripe_subscription_id="sub_order",
        plan=price.plan,
        price=price,
        status=status,
    )


def test_invoice_payment_failed_does_not_resurrect_a_cancelled_subscription() -> None:
    """A late or replayed `invoice.payment_failed` arriving after
    cancellation must not flip `canceled` to `past_due` — `past_due` is an
    entitling status, so that would hand the org its paid features back."""
    org = _org()
    price = _price()
    _existing_subscription(org, price, status="canceled")

    webhooks._handle_invoice_payment_failed({"customer": "cus_order"}, LATE)

    assert Subscription.objects.get().status == "canceled"


@pytest.mark.parametrize("status", ["incomplete", "incomplete_expired", "unpaid"])
def test_invoice_payment_failed_leaves_other_terminal_statuses_alone(status: str) -> None:
    org = _org()
    price = _price()
    _existing_subscription(org, price, status=status)

    webhooks._handle_invoice_payment_failed({"customer": "cus_order"}, LATE)

    assert Subscription.objects.get().status == status


@pytest.mark.parametrize("status", ["active", "trialing", "past_due"])
def test_invoice_payment_failed_still_starts_dunning_from_a_live_status(status: str) -> None:
    org = _org()
    price = _price()
    _existing_subscription(org, price, status=status)

    webhooks._handle_invoice_payment_failed({"customer": "cus_order"}, LATE)

    assert Subscription.objects.get().status == "past_due"


def test_invoice_payment_failed_with_no_subscription_row_is_a_no_op() -> None:
    _org()
    _price()

    webhooks._handle_invoice_payment_failed({"customer": "cus_order"}, LATE)

    assert not Subscription.objects.exists()


def test_a_late_invoice_payment_failed_loses_to_a_newer_subscription_event() -> None:
    """The LWW guard the subscription handler uses now covers the invoice
    handlers too: an older event can't overwrite what a newer one wrote."""
    _org()
    _price()

    webhooks._handle_subscription_event(_subscription_object("active"), LATE)
    webhooks._handle_invoice_payment_failed({"customer": "cus_order"}, EARLY)

    assert Subscription.objects.get().status == "active"


def test_a_late_invoice_paid_loses_to_a_newer_subscription_event() -> None:
    _org()
    _price()

    webhooks._handle_subscription_event(_subscription_object("past_due"), LATE)
    webhooks._handle_invoice_paid({"customer": "cus_order"}, EARLY)

    assert Subscription.objects.get().status == "past_due"


def test_a_newer_invoice_event_applies_over_an_older_subscription_event() -> None:
    _org()
    _price()

    webhooks._handle_subscription_event(_subscription_object("active"), EARLY)
    webhooks._handle_invoice_payment_failed({"customer": "cus_order"}, LATE)

    subscription = Subscription.objects.get()
    assert subscription.status == "past_due"
    assert subscription.stripe_updated_at is not None


def test_invoice_events_with_no_event_created_timestamp_still_apply() -> None:
    """Same escape hatch the subscription handler has: a hand-built
    payload with no `created` isn't dropped by the guard."""
    org = _org()
    price = _price()
    _existing_subscription(org, price, status="active")

    webhooks._handle_invoice_payment_failed({"customer": "cus_order"}, None)

    assert Subscription.objects.get().status == "past_due"
