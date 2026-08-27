"""``billing/credits.py`` — the arithmetic (docs/plans/phase-4.md A.1,
A.3, A.5). Concurrency (A.2) and the rebuild command (A.3) each get
their own module: concurrency needs real transactions across threads,
and the rebuild command exercises `manage.py`, not just the module.
"""

import pytest
from django.db.models import Sum
from django.test import override_settings

from keel.billing import credits
from keel.billing.models import CreditBalance, CreditLedgerEntry, Plan, Price, Subscription
from keel.billing.tests.factories import make_organization, make_user
from keel.core.exceptions import PaymentRequired

pytestmark = pytest.mark.django_db


def _ledger_sum(organization) -> int:
    total = CreditLedgerEntry.objects.filter(organization=organization).aggregate(
        total=Sum("amount")
    )["total"]
    return total or 0


def _balance_row(organization) -> CreditBalance:
    return CreditBalance.objects.get(organization=organization)


def _with_subscription(organization, *, daily_credit_cap: int) -> Subscription:
    plan = Plan.objects.create(
        code=f"plan-{organization.pk}",
        name="Test plan",
        entitlements={"daily_credit_cap": daily_credit_cap},
    )
    price = Price.objects.create(
        plan=plan,
        stripe_price_id=f"price_{organization.pk}",
        interval=Price.INTERVAL_MONTH,
        unit_amount=1000,
    )
    return Subscription.objects.create(
        organization=organization,
        stripe_subscription_id=f"sub_{organization.pk}",
        plan=plan,
        price=price,
        status="active",
    )


class TestBalanceRead:
    def test_get_balance_creates_a_zero_row_when_missing(self):
        org = make_organization()

        assert credits.get_balance(org) == 0
        assert CreditBalance.objects.filter(organization=org).exists()

    def test_get_balance_reads_the_existing_row(self):
        org = make_organization()
        CreditBalance.objects.create(organization=org, balance=42)

        assert credits.get_balance(org) == 42


class TestGrant:
    def test_grant_increases_balance_and_writes_a_ledger_row(self):
        org = make_organization()

        entry = credits.grant(org, 100, reason="plan allowance")

        assert entry.kind == CreditLedgerEntry.KIND_GRANT
        assert entry.amount == 100
        assert credits.get_balance(org) == 100
        assert _balance_row(org).balance == _ledger_sum(org)

    def test_grant_rejects_non_positive_amount(self):
        org = make_organization()

        with pytest.raises(ValueError):
            credits.grant(org, 0)
        with pytest.raises(ValueError):
            credits.grant(org, -5)


class TestHold:
    def test_hold_reserves_credits_against_a_sufficient_balance(self):
        org = make_organization()
        credits.grant(org, 50)

        entry = credits.hold(org, 20)

        assert entry.kind == CreditLedgerEntry.KIND_HOLD
        assert entry.amount == -20
        assert credits.get_balance(org) == 30
        assert _balance_row(org).balance == _ledger_sum(org)

    def test_hold_against_an_insufficient_balance_is_a_402_and_changes_nothing(self):
        org = make_organization()
        credits.grant(org, 10)

        with pytest.raises(PaymentRequired) as exc_info:
            credits.hold(org, 20)

        assert exc_info.value.status_code == 402
        assert exc_info.value.code == "insufficient_credits"
        assert exc_info.value.details == {"balance": 10, "amount": 20}
        assert credits.get_balance(org) == 10

    def test_hold_rejects_non_positive_amount(self):
        org = make_organization()

        with pytest.raises(ValueError):
            credits.hold(org, 0)

    def test_hold_links_the_job_and_actor(self):
        org = make_organization()
        credits.grant(org, 50)
        actor = make_user()

        entry = credits.hold(org, 5, actor=actor)

        assert entry.actor == actor
        assert entry.job is None


class TestConsume:
    def test_consume_is_an_immediate_final_debit(self):
        org = make_organization()
        credits.grant(org, 50)

        entry = credits.consume(org, 15)

        assert entry.kind == CreditLedgerEntry.KIND_CONSUME
        assert entry.amount == -15
        assert credits.get_balance(org) == 35
        assert _balance_row(org).balance == _ledger_sum(org)

    def test_consume_against_an_insufficient_balance_is_a_402(self):
        org = make_organization()

        with pytest.raises(PaymentRequired):
            credits.consume(org, 1)


class TestReleaseAndRefund:
    def test_a_job_finishing_under_estimate_releases_the_remainder(self):
        org = make_organization()
        credits.grant(org, 100)
        hold_entry = credits.hold(org, 30)

        release_entry = credits.release(org, hold_entry, 12)

        assert release_entry.kind == CreditLedgerEntry.KIND_RELEASE
        assert release_entry.amount == 12
        # Held 30, actually used 30 - 12 = 18.
        assert credits.get_balance(org) == 100 - 18
        assert _balance_row(org).balance == _ledger_sum(org)

    def test_release_cannot_exceed_the_held_amount(self):
        org = make_organization()
        credits.grant(org, 100)
        hold_entry = credits.hold(org, 30)

        with pytest.raises(ValueError):
            credits.release(org, hold_entry, 31)

    def test_release_rejects_non_positive_amount(self):
        org = make_organization()
        credits.grant(org, 100)
        hold_entry = credits.hold(org, 30)

        with pytest.raises(ValueError):
            credits.release(org, hold_entry, 0)

    def test_a_failed_jobs_hold_is_fully_refunded(self):
        org = make_organization()
        credits.grant(org, 100)
        hold_entry = credits.hold(org, 30)

        refund_entry = credits.refund(org, hold_entry)

        assert refund_entry.kind == CreditLedgerEntry.KIND_REFUND
        assert refund_entry.amount == 30
        assert credits.get_balance(org) == 100
        assert _balance_row(org).balance == _ledger_sum(org)


class TestAdjust:
    def test_adjust_requires_a_reason(self):
        org = make_organization()
        actor = make_user()

        with pytest.raises(ValueError):
            credits.adjust(org, 10, reason="", actor=actor)

    def test_adjust_rejects_a_zero_amount(self):
        org = make_organization()
        actor = make_user()

        with pytest.raises(ValueError):
            credits.adjust(org, 0, reason="correction", actor=actor)

    def test_adjust_writes_a_reasoned_actorful_row_and_updates_balance(self):
        org = make_organization()
        actor = make_user()
        credits.grant(org, 20)

        entry = credits.adjust(org, -7, reason="chargeback", actor=actor)

        assert entry.kind == CreditLedgerEntry.KIND_ADJUSTMENT
        assert entry.amount == -7
        assert entry.reason == "chargeback"
        assert entry.actor == actor
        assert credits.get_balance(org) == 20 - 7
        assert _balance_row(org).balance == _ledger_sum(org)

    def test_adjust_cannot_take_the_balance_below_zero(self):
        """ddia#5/#23: unlike every other debit in this module, a
        clawback used to have no floor at all — the database's
        ``CHECK (balance >= 0)`` is the backstop; this is the readable
        ``PaymentRequired`` the caller actually gets."""
        org = make_organization()
        actor = make_user()
        credits.grant(org, 5)

        with pytest.raises(PaymentRequired) as exc_info:
            credits.adjust(org, -6, reason="chargeback exceeds balance", actor=actor)

        assert exc_info.value.code == "adjustment_exceeds_balance"
        assert credits.get_balance(org) == 5

    @pytest.mark.django_db(transaction=True)
    def test_adjust_records_an_audit_entry_on_commit(self):
        from django.db import transaction as db_transaction

        from keel.core import audit as audit_module

        org = make_organization()
        actor = make_user()
        recorded = []
        audit_module.set_recorder(recorded.append)
        try:
            with db_transaction.atomic():
                credits.adjust(org, 5, reason="goodwill credit", actor=actor)
        finally:
            audit_module.set_recorder(audit_module._default_recorder)

        assert len(recorded) == 1
        record = recorded[0]
        assert record.action == "credits.adjustment"
        assert record.actor == actor


class TestEstimate:
    def test_estimate_is_read_only(self):
        org = make_organization()
        credits.grant(org, 40)

        before = CreditLedgerEntry.objects.filter(organization=org).count()
        result = credits.estimate(org, 10)
        after = CreditLedgerEntry.objects.filter(organization=org).count()

        assert after == before
        assert result == {
            "balance": 40,
            "amount": 10,
            "cap": None,
            "spent_today": 0,
            "sufficient": True,
        }

    def test_estimate_reports_insufficient_when_balance_is_too_low(self):
        org = make_organization()
        credits.grant(org, 5)

        result = credits.estimate(org, 10)

        assert result["sufficient"] is False

    def test_estimate_rejects_negative_amount(self):
        org = make_organization()

        with pytest.raises(ValueError):
            credits.estimate(org, -1)


class TestDailyCap:
    def test_no_subscription_means_no_cap(self):
        org = make_organization()
        credits.grant(org, 1_000_000)

        credits.hold(org, 999_999)  # would not raise even without a subscription

        assert credits.get_balance(org) == 1

    def test_a_hold_within_the_cap_succeeds(self):
        org = make_organization()
        _with_subscription(org, daily_credit_cap=100)
        credits.grant(org, 1000)

        credits.hold(org, 60)

        assert credits.get_balance(org) == 940

    def test_a_hold_that_would_exceed_the_cap_is_a_402_with_the_cap_in_details(self):
        org = make_organization()
        _with_subscription(org, daily_credit_cap=100)
        credits.grant(org, 1000)
        credits.hold(org, 60)

        with pytest.raises(PaymentRequired) as exc_info:
            credits.hold(org, 50)

        assert exc_info.value.status_code == 402
        assert exc_info.value.code == "daily_cap_exceeded"
        assert exc_info.value.details == {"cap": 100, "spent": 60, "amount": 50}
        # Nothing changed - the balance still only reflects the first hold.
        assert credits.get_balance(org) == 940

    def test_consume_is_also_capped(self):
        org = make_organization()
        _with_subscription(org, daily_credit_cap=10)
        credits.grant(org, 1000)

        with pytest.raises(PaymentRequired):
            credits.consume(org, 11)

    def test_release_and_refund_do_not_count_against_the_cap(self):
        org = make_organization()
        _with_subscription(org, daily_credit_cap=10)
        credits.grant(org, 1000)
        hold_entry = credits.hold(org, 10)

        # Releasing/refunding are credits, not debits - they never check the cap.
        credits.release(org, hold_entry, 4)

        assert credits.get_balance(org) == 994


class TestCreditsEnabled:
    def test_defaults_to_disabled(self, settings):
        del settings.BILLING_CREDITS
        assert credits.credits_enabled() is False

    @override_settings(BILLING_CREDITS=False)
    def test_off(self):
        assert credits.credits_enabled() is False

    @override_settings(BILLING_CREDITS=True)
    def test_on(self):
        assert credits.credits_enabled() is True
