"""``manage.py sync_stripe_plans`` (docs/plans/phase-4.md B.1) — wires
``stripe_client.fetch_products_and_prices`` to ``sync_plans_from_stripe``.
The Stripe I/O itself is monkeypatched: no real Stripe call, no
stripe-mock (PRD §4, "No credentials")."""

from io import StringIO

import pytest
from django.core.management import call_command

from keel.billing import stripe_client
from keel.billing.models import Plan

pytestmark = pytest.mark.django_db


def test_command_syncs_plans_from_fetched_products(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch() -> list[dict]:
        return [
            {
                "id": "prod_starter",
                "name": "Starter",
                "metadata": {"code": "starter"},
                "prices": [
                    {
                        "id": "price_starter_m",
                        "unit_amount": 1900,
                        "currency": "aud",
                        "recurring": {"interval": "month"},
                    }
                ],
            }
        ]

    monkeypatch.setattr(stripe_client, "fetch_products_and_prices", fake_fetch)

    out = StringIO()
    call_command("sync_stripe_plans", stdout=out)

    assert Plan.objects.filter(code="starter", is_active=True).exists()
    assert "Synced 1 plan(s), 1 price(s)" in out.getvalue()


def test_command_without_stripe_secret_key_raises_improperly_configured(settings) -> None:
    settings.STRIPE_SECRET_KEY = ""

    with pytest.raises(Exception) as exc_info:
        call_command("sync_stripe_plans")

    assert "STRIPE_SECRET_KEY" in str(exc_info.value)
