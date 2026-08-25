"""``python manage.py sync_stripe_plans`` (docs/plans/phase-4.md B.1). Run
nightly by beat once Phase 5 schedules it (PRD §5, "Scheduled jobs")."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from keel.billing import stripe_client
from keel.billing.services import sync_plans_from_stripe


class Command(BaseCommand):
    help = "Sync Plan/Price rows from Stripe — Stripe is the source of truth."

    def add_arguments(self, parser: CommandParser) -> None:
        pass

    def handle(self, *args: Any, **options: Any) -> None:
        products = stripe_client.fetch_products_and_prices()
        result = sync_plans_from_stripe(products)
        self.stdout.write(
            self.style.SUCCESS(
                "Synced {plans_synced} plan(s), {prices_synced} price(s); "
                "deactivated {plans_deactivated} plan(s), "
                "{prices_deactivated} price(s).".format(**result)
            )
        )
