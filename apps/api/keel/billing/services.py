"""Billing services (docs/plans/phase-4.md B.1-B.6). Starts with plan/price
sync — the part that is pure arithmetic over rows, same shape as
``organizations/services.py``: one function per operation, transactional,
no Stripe I/O inside it (``stripe_client.py`` owns that seam)."""

from typing import Any

from django.db import transaction

from keel.billing.models import Plan, Price


class MissingPlanCode(Exception):
    """A Stripe Product with no ``metadata.code`` cannot become a Plan —
    ``Plan.code`` is what the rest of the app (entitlements, seat sync,
    the pricing page) addresses a plan by, and Stripe assigns no equivalent
    stable, human-chosen slug on its own."""

    def __init__(self, stripe_product_id: str) -> None:
        self.stripe_product_id = stripe_product_id
        super().__init__(
            f"Stripe product {stripe_product_id!r} has no metadata['code']. "
            "Set a 'code' metadata key on the product in Stripe before syncing."
        )


@transaction.atomic
def sync_plans_from_stripe(products: list[dict[str, Any]]) -> dict[str, int]:
    """Upsert ``Plan``/``Price`` rows from ``products`` — the normalised
    shape ``stripe_client.fetch_products_and_prices`` returns. Stripe is the
    source of truth: a plan or price no longer present and active in
    ``products`` is deactivated locally, never deleted (other rows —
    ``Subscription``, ``CreditLedgerEntry`` — reference these by FK).

    Returns counts for the management command to report.
    """
    seen_product_ids: set[str] = set()
    seen_price_ids: set[str] = set()
    plans_synced = 0
    prices_synced = 0

    for product in products:
        stripe_product_id = product["id"]
        code = product.get("metadata", {}).get("code")
        if not code:
            raise MissingPlanCode(stripe_product_id)
        seen_product_ids.add(stripe_product_id)

        plan, _ = Plan.objects.update_or_create(
            stripe_product_id=stripe_product_id,
            defaults={"code": code, "name": product["name"], "is_active": True},
        )
        plans_synced += 1

        for price in product.get("prices", []):
            stripe_price_id = price["id"]
            interval = price.get("recurring", {}).get("interval", Price.INTERVAL_MONTH)
            seen_price_ids.add(stripe_price_id)
            Price.objects.update_or_create(
                stripe_price_id=stripe_price_id,
                defaults={
                    "plan": plan,
                    "interval": interval,
                    "unit_amount": price["unit_amount"],
                    "currency": price["currency"].upper(),
                    "is_active": True,
                },
            )
            prices_synced += 1

    deactivated_plans = (
        Plan.objects.exclude(stripe_product_id="")
        .exclude(stripe_product_id__in=seen_product_ids)
        .filter(is_active=True)
        .update(is_active=False)
    )
    deactivated_prices = (
        Price.objects.exclude(stripe_price_id__in=seen_price_ids)
        .filter(is_active=True)
        .update(is_active=False)
    )

    return {
        "plans_synced": plans_synced,
        "prices_synced": prices_synced,
        "plans_deactivated": deactivated_plans,
        "prices_deactivated": deactivated_prices,
    }
