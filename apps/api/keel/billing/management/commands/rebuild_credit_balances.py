"""Rebuild ``CreditBalance`` from ``CreditLedgerEntry`` (PRD §4 "Credits
— the metered-billing primitive"; docs/plans/phase-4.md A.3): "a
management command rebuilds ``CreditBalance`` from the ledger and
reproduces the same number."

The ledger is the truth; the balance row is only ever an index of it, so
this command exists to prove — and, if the index has ever drifted, to
restore — that the index still says what the ledger says.
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import models, transaction

from keel.billing.models import CreditBalance, CreditLedgerEntry
from keel.organizations.models import Organization


class Command(BaseCommand):
    help = "Rebuild every organisation's CreditBalance from the CreditLedgerEntry ledger."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--organization",
            default=None,
            help="Rebuild a single organisation by id instead of every organisation.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        organizations = Organization.objects.all()
        organization_id = options.get("organization")
        if organization_id:
            organizations = organizations.filter(id=organization_id)

        rebuilt = 0
        for organization in organizations.iterator():
            with transaction.atomic():
                total = (
                    CreditLedgerEntry.objects.filter(organization=organization).aggregate(
                        total=models.Sum("amount")
                    )["total"]
                    or 0
                )
                balance_row, _ = CreditBalance.objects.select_for_update().get_or_create(
                    organization=organization
                )
                balance_row.balance = total
                balance_row.save(update_fields=["balance", "updated_at"])
            rebuilt += 1
            self.stdout.write(f"{organization.id}: {total}")

        self.stdout.write(self.style.SUCCESS(f"Rebuilt {rebuilt} organisation balance(s)."))
