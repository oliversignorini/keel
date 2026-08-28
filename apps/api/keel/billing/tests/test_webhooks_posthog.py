"""Billing webhook handlers capture to PostHog (PRD §4 Integration
points: "server-side capture helper for billing events").
Handlers called directly — same shape as
``test_tasks.py``'s handler-level tests — with ``capture_billing_event``
patched to assert the call shape, since no PostHog key exists (see
``keel.core.posthog``'s docstring)."""

from unittest.mock import patch

import pytest

from keel.accounts.models import User
from keel.billing import webhooks
from keel.billing.models import Plan, Price
from keel.organizations.models import Organization

pytestmark = pytest.mark.django_db


def _org(customer_id: str = "cus_ph") -> Organization:
    creator = User.objects.create_user(email="owner-ph@example.com", password="s3cret-pass")
    return Organization.objects.create(
        name="Acme", slug="acme-ph", created_by=creator, stripe_customer_id=customer_id
    )


def _price() -> Price:
    plan = Plan.objects.create(code="starter", name="Starter", stripe_product_id="prod_ph")
    return Price.objects.create(
        plan=plan,
        stripe_price_id="price_ph",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1900,
        currency="AUD",
    )


def test_subscription_event_captures_a_billing_event() -> None:
    org = _org()
    price = _price()

    with patch("keel.billing.webhooks.capture_billing_event") as mock_capture:
        webhooks._handle_subscription_event(
            {
                "id": "sub_1",
                "customer": org.stripe_customer_id,
                "status": "active",
                "items": {"data": [{"price": {"id": price.stripe_price_id}, "quantity": 1}]},
            },
            None,
        )

    mock_capture.assert_called_once_with(
        distinct_id=str(org.created_by_id),
        event="subscription_active",
        properties={
            "organization_id": str(org.id),
            "plan_code": "starter",
            "stripe_subscription_id": "sub_1",
        },
    )


def test_invoice_paid_captures_a_billing_event() -> None:
    org = _org()

    with patch("keel.billing.webhooks.capture_billing_event") as mock_capture:
        webhooks._handle_invoice_paid({"customer": org.stripe_customer_id}, None)

    mock_capture.assert_called_once_with(
        distinct_id=str(org.created_by_id),
        event="invoice_paid",
        properties={"organization_id": str(org.id)},
    )


def test_invoice_payment_failed_captures_a_billing_event() -> None:
    org = _org()

    with patch("keel.billing.webhooks.capture_billing_event") as mock_capture:
        webhooks._handle_invoice_payment_failed({"customer": org.stripe_customer_id}, None)

    mock_capture.assert_called_once_with(
        distinct_id=str(org.created_by_id),
        event="invoice_payment_failed",
        properties={"organization_id": str(org.id)},
    )


def test_invoice_paid_for_an_unknown_customer_does_not_capture() -> None:
    with patch("keel.billing.webhooks.capture_billing_event") as mock_capture:
        webhooks._handle_invoice_paid({"customer": "cus_does_not_exist"}, None)

    mock_capture.assert_not_called()
