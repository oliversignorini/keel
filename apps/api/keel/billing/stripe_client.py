"""The Stripe I/O boundary for plan/price sync (docs/plans/phase-4.md B.1).

Thin on purpose: this module's only job is turning Stripe's API into the
plain dicts ``keel.billing.services.sync_plans_from_stripe`` consumes.
Nothing here has business logic, and nothing here is unit tested against
real Stripe — that's what ``services.sync_plans_from_stripe`` tests are
for, using recorded fixture dicts. See PRD §7 "adapters" coverage note:
this module is deliberately excluded from a coverage gate.
"""

from typing import Any

import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _client() -> Any:
    if not settings.STRIPE_SECRET_KEY:
        raise ImproperlyConfigured(
            "settings.STRIPE_SECRET_KEY is not configured. Set STRIPE_SECRET_KEY "
            "before calling keel.billing.stripe_client — there is no offline "
            "fallback, by design (PRD §4, 'no credentials is not a blocker for "
            "any acceptance criterion' means tests inject fixtures, not that "
            "this module tolerates a missing key at call time)."
        )
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


def fetch_products_and_prices() -> list[dict[str, Any]]:
    """Every active Stripe Product, each with its active Prices attached,
    normalised to the plain-dict shape ``sync_plans_from_stripe`` expects:

    ``{"id": str, "name": str, "metadata": dict, "prices": [
        {"id": str, "unit_amount": int, "currency": str, "recurring": {"interval": str}}
    ]}``
    """
    client = _client()
    products = client.products.list({"active": True, "limit": 100})
    normalized: list[dict[str, Any]] = []
    for product in products.auto_paging_iter():
        prices = client.prices.list({"product": product.id, "active": True, "limit": 100})
        normalized.append(
            {
                "id": product.id,
                "name": product.name,
                "metadata": dict(product.metadata or {}),
                "prices": [
                    {
                        "id": price.id,
                        "unit_amount": price.unit_amount,
                        "currency": price.currency,
                        "recurring": dict(price.recurring or {}),
                    }
                    for price in prices.auto_paging_iter()
                ],
            }
        )
    return normalized
