"""Rebuild ``CreditBalance`` from ``CreditLedgerEntry``: a management
command rebuilds ``CreditBalance`` from the ledger and reproduces the
same number.

The ledger is the truth; the balance row is only ever an index of it, so
this command exists to prove — and, if the index has ever drifted, to
restore — that the index still says what the ledger says.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from keel.billing.models import CreditBalance, CreditLedgerEntry
from keel.billing.services import check_credit_balances
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
                "exit non-zero if any organisation has drifted (report, don't repair)."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        organization_id = options.get("organization")
        check = options.get("check", False)

        if check:
            # Shared with the nightly check_credit_balances_task beat task
            # — one comparison, two callers.
            drifted = check_credit_balances(organization_id=organization_id)
            for row in drifted:
                self.stderr.write(
                    self.style.WARNING(
                        f"{row['organization_id']}: drift — ledger={row['ledger_total']} "
                        f"balance={row['balance']}"
                    )
                )
            if drifted:
                raise CommandError(
                    f"{len(drifted)} organisation balance(s) drifted from the ledger."
                )
            self.stdout.write(self.style.SUCCESS("No drift detected."))
            return

        organizations = Organization.objects.all()
        if organization_id:
            organizations = organizations.filter(id=organization_id)

        rebuilt = 0
        for organization in organizations.iterator():
            with transaction.atomic():
                # Lock before SUM: the balance row must be locked
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
                balance_row.balance = total
                balance_row.save(update_fields=["balance", "updated_at"])
            rebuilt += 1
            self.stdout.write(f"{organization.id}: {total}")

        self.stdout.write(self.style.SUCCESS(f"Rebuilt {rebuilt} organisation balance(s)."))
