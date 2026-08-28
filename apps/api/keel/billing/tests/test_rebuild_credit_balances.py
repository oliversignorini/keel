"""``rebuild_credit_balances``: "a management
command rebuilds ``CreditBalance`` from the ledger and reproduces the
same number.\""""

import pytest
from django.core.management import CommandError, call_command

from keel.billing import credits
from keel.billing.models import CreditBalance
from keel.billing.services import check_credit_balances
from keel.billing.tests.factories import make_organization

pytestmark = pytest.mark.django_db


def test_rebuild_reproduces_the_correct_balance_after_drift():
    org = make_organization()
    credits.grant(org, 100)
    hold_entry = credits.hold(org, 30)
    credits.release(org, hold_entry, 10)
    correct_balance = credits.get_balance(org)  # 100 - 20 = 80

    # Simulate index drift: an out-of-band write against the summary row,
    # never a real code path but exactly what the ledger's SUM(amount)
    # is supposed to be robust against.
    balance_row = CreditBalance.objects.get(organization=org)
    balance_row.balance = 999_999
    balance_row.save(update_fields=["balance"])

    call_command("rebuild_credit_balances")

    balance_row.refresh_from_db()
    assert balance_row.balance == correct_balance == 80


def test_rebuild_can_target_a_single_organization():
    org_a = make_organization()
    org_b = make_organization()
    credits.grant(org_a, 50)
    credits.grant(org_b, 70)
    CreditBalance.objects.filter(organization=org_a).update(balance=0)
    CreditBalance.objects.filter(organization=org_b).update(balance=0)

    call_command("rebuild_credit_balances", organization=str(org_a.pk))

    assert CreditBalance.objects.get(organization=org_a).balance == 50
    assert CreditBalance.objects.get(organization=org_b).balance == 0


def test_rebuild_creates_the_balance_row_when_one_never_existed():
    org = make_organization()
    credits.grant(org, 15)
    CreditBalance.objects.filter(organization=org).delete()

    call_command("rebuild_credit_balances")

    assert CreditBalance.objects.get(organization=org).balance == 15


# --- --check: report, don't repair -------------------------------------------


def test_check_mode_reports_no_drift_and_writes_nothing():
    org = make_organization()
    credits.grant(org, 40)

    call_command("rebuild_credit_balances", check=True)

    assert CreditBalance.objects.get(organization=org).balance == 40


def test_check_mode_exits_non_zero_and_leaves_the_drifted_balance_untouched():
    org = make_organization()
    credits.grant(org, 40)
    CreditBalance.objects.filter(organization=org).update(balance=999)

    with pytest.raises(CommandError):
        call_command("rebuild_credit_balances", check=True)

    assert CreditBalance.objects.get(organization=org).balance == 999


def test_check_credit_balances_service_reports_drift_by_organization():
    org_a = make_organization()
    org_b = make_organization()
    credits.grant(org_a, 40)
    credits.grant(org_b, 10)
    CreditBalance.objects.filter(organization=org_a).update(balance=999)

    drifted = check_credit_balances()

    assert [row["organization_id"] for row in drifted] == [str(org_a.id)]
    assert drifted[0]["ledger_total"] == 40
    assert drifted[0]["balance"] == 999


def test_check_credit_balances_service_can_target_a_single_organization():
    org_a = make_organization()
    org_b = make_organization()
    credits.grant(org_a, 40)
    credits.grant(org_b, 10)
    CreditBalance.objects.filter(organization=org_a).update(balance=999)
    CreditBalance.objects.filter(organization=org_b).update(balance=999)

    drifted = check_credit_balances(organization_id=str(org_b.id))

    assert [row["organization_id"] for row in drifted] == [str(org_b.id)]
