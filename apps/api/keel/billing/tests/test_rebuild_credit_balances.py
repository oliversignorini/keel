"""``rebuild_credit_balances`` (docs/plans/phase-4.md A.3): "a management
command rebuilds ``CreditBalance`` from the ledger and reproduces the
same number.\""""

import pytest
from django.core.management import call_command

from keel.billing import credits
from keel.billing.models import CreditBalance
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
