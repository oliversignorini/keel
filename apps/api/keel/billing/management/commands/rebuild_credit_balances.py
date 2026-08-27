"""Rebuild ``CreditBalance`` from ``CreditLedgerEntry`` (PRD §4 "Credits
— the metered-billing primitive"; docs/plans/phase-4.md A.3): "a
management command rebuilds ``CreditBalance`` from the ledger and
reproduces the same number."

The ledger is the truth; the balance row is only ever an index of it, so
this command exists to prove — and, if the index has ever drifted, to
restore — that the index still says what the ledger says.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError
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
        parser.add_argument(
            "--check",
            action="store_true",
            help=(
                "Compare the ledger against the current CreditBalance without writing; "
                "exit non-zero if any organisation has drifted (ddia#4: report, don't repair)."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        organizations = Organization.objects.all()
        organization_id = options.get("organization")
        if organization_id:
            organizations = organizations.filter(id=organization_id)
        check = options.get("check", False)

        rebuilt = 0
        drifted = 0
        for organization in organizations.iterator():
            with transaction.atomic():
                # Lock before SUM (ddia#3): the balance row must be locked
                # before the ledger is aggregated, not after, or a debit
                # that commits in between is silently erased by the write
                # below — the exact thing this command exists to catch.
                balance_row, _ = CreditBalance.objects.select_for_update().get_or_create(
                    organization=organization
                )
                total = (
                    CreditLedgerEntry.objects.filter(organization=organization).aggregate(
                        total=models.Sum("amount")
                    )["total"]
                    or 0
                )
                if check:
                    if balance_row.balance != total:
                        drifted += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"{organization.id}: drift — ledger={total} "
                                f"balance={balance_row.balance}"
                            )
                        )
                    continue
                balance_row.balance = total
                balance_row.save(update_fields=["balance", "updated_at"])
            rebuilt += 1
            self.stdout.write(f"{organization.id}: {total}")

        if check:
            if drifted:
                raise CommandError(f"{drifted} organisation balance(s) drifted from the ledger.")
            self.stdout.write(self.style.SUCCESS("No drift detected."))
            return

        self.stdout.write(self.style.SUCCESS(f"Rebuilt {rebuilt} organisation balance(s)."))
