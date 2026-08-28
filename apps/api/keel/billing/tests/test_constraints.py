"""Database-level invariants: ``CHECK`` constraints on the credit ledger
and ``PROTECT`` on ``CreditLedgerEntry.organization``/``job``, plus
``Plan.entitlements`` shape validation.

These deliberately write around the service layer (``credits.py`` already
never produces an invalid row — that's what the module docstring claims
and the coverage floor tests) to prove the *database* refuses it too,
regardless of which code path wrote the row.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from keel.billing import credits
from keel.billing.models import CreditBalance, CreditLedgerEntry, Plan
from keel.billing.tests.factories import make_organization

pytestmark = pytest.mark.django_db


# --- CreditBalance.balance >= 0 ---------------------------------------------


def test_credit_balance_cannot_go_negative_at_the_database_level():
    org = make_organization()
    credits.get_balance(org)  # ensures the CreditBalance row exists
    balance_row = CreditBalance.objects.get(organization=org)

    balance_row.balance = -1
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            balance_row.save(update_fields=["balance"])


# --- CreditLedgerEntry kind/sign constraint ---------------------------------


def test_a_hold_with_a_positive_amount_is_rejected():
    org = make_organization()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CreditLedgerEntry.objects.create(
                organization=org, kind=CreditLedgerEntry.KIND_HOLD, amount=10
            )


def test_a_grant_with_a_negative_amount_is_rejected():
    org = make_organization()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CreditLedgerEntry.objects.create(
                organization=org, kind=CreditLedgerEntry.KIND_GRANT, amount=-10
            )


def test_a_zero_amount_adjustment_is_rejected():
    org = make_organization()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CreditLedgerEntry.objects.create(
                organization=org, kind=CreditLedgerEntry.KIND_ADJUSTMENT, amount=0
            )


def test_a_negative_adjustment_is_allowed():
    org = make_organization()

    entry = CreditLedgerEntry.objects.create(
        organization=org, kind=CreditLedgerEntry.KIND_ADJUSTMENT, amount=-5, reason="clawback"
    )

    assert entry.amount == -5


# --- PROTECT on organization/job --------------------------------------------


def test_organization_cannot_be_hard_deleted_while_ledger_entries_reference_it():
    org = make_organization()
    CreditLedgerEntry.objects.create(organization=org, kind=CreditLedgerEntry.KIND_GRANT, amount=5)

    with pytest.raises(ProtectedError):
        org.delete()


def test_job_cannot_be_hard_deleted_while_a_ledger_entry_references_it():
    from keel.jobs.tests.factories import job_factory

    org = make_organization()
    job = job_factory(org)
    CreditLedgerEntry.objects.create(
        organization=org, job=job, kind=CreditLedgerEntry.KIND_HOLD, amount=-5
    )

    with pytest.raises(ProtectedError):
        job.delete()


# --- Plan.entitlements shape validation -------------------------------------


def test_plan_entitlements_rejects_an_unknown_top_level_key():
    with pytest.raises(ValidationError):
        Plan.objects.create(
            code="typo-plan", name="Typo Plan", entitlements={"limmits": {"seats": 5}}
        )


def test_plan_entitlements_rejects_a_non_integer_limit_value():
    with pytest.raises(ValidationError):
        Plan.objects.create(
            code="bad-limit-plan", name="Bad Limit Plan", entitlements={"limits": {"seats": "lots"}}
        )


def test_plan_entitlements_accepts_the_documented_shape():
    plan = Plan.objects.create(
        code="valid-plan",
        name="Valid Plan",
        entitlements={"features": ["api_access"], "limits": {"seats": 5}, "daily_credit_cap": 100},
    )

    assert plan.entitlements["limits"]["seats"] == 5


def test_plan_entitlements_accepts_the_daily_cap_only_shape():
    """``credits._daily_cap`` reads ``daily_credit_cap`` directly off a
    plan with no ``features``/``limits`` at all — a legitimate, narrower
    use of the same field."""
    plan = Plan.objects.create(
        code="cap-only-plan", name="Cap Only Plan", entitlements={"daily_credit_cap": 50}
    )

    assert plan.entitlements == {"daily_credit_cap": 50}
