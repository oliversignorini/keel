"""Django admin — the operator adjustment flow (docs/plans/phase-4.md
A.4): requires a reason, records the actor, and is the only way an
adjustment entry gets written."""

import pytest
from django.test import Client
from django.urls import reverse

from keel.billing import credits
from keel.billing.models import CreditBalance, CreditLedgerEntry
from keel.billing.tests.factories import make_organization, make_user

pytestmark = pytest.mark.django_db


def _staff_client() -> tuple[Client, "object"]:
    operator = make_user()
    operator.is_staff = True
    operator.is_superuser = True
    operator.save()
    client = Client()
    client.force_login(operator)
    return client, operator


def test_credit_ledger_entry_admin_is_read_only():
    client, _ = _staff_client()
    org = make_organization()
    entry = credits.grant(org, 10)

    add_response = client.get(reverse("admin:billing_creditledgerentry_add"))
    # A superuser can still open the change page, but has_change_permission
    # being False makes Django render it read-only rather than editable
    # (403 on add is the harder guarantee — there is no per-object
    # exception for it the way view/change has one for superusers).
    client.post(
        reverse("admin:billing_creditledgerentry_change", args=[entry.pk]),
        data={"amount": "999"},
    )

    assert add_response.status_code == 403
    entry.refresh_from_db()
    assert entry.amount == 10


def test_adjust_form_requires_a_reason():
    client, _ = _staff_client()
    org = make_organization()
    CreditBalance.objects.create(organization=org, balance=0)

    response = client.post(
        reverse("admin:billing_creditbalance_adjust", args=[org.pk]),
        data={"amount": "10", "reason": ""},
    )

    assert response.status_code == 200  # re-rendered with a validation error
    assert not CreditLedgerEntry.objects.filter(organization=org).exists()


def test_adjust_form_records_the_operator_as_actor_and_updates_balance():
    client, operator = _staff_client()
    org = make_organization()
    CreditBalance.objects.create(organization=org, balance=5)

    response = client.post(
        reverse("admin:billing_creditbalance_adjust", args=[org.pk]),
        data={"amount": "20", "reason": "goodwill credit"},
    )

    assert response.status_code == 302
    entry = CreditLedgerEntry.objects.get(organization=org, kind=CreditLedgerEntry.KIND_ADJUSTMENT)
    assert entry.amount == 20
    assert entry.reason == "goodwill credit"
    assert entry.actor == operator
    assert CreditBalance.objects.get(organization=org).balance == 25


def test_adjust_form_rejects_a_zero_amount():
    client, _ = _staff_client()
    org = make_organization()
    CreditBalance.objects.create(organization=org, balance=5)

    response = client.post(
        reverse("admin:billing_creditbalance_adjust", args=[org.pk]),
        data={"amount": "0", "reason": "typo correction"},
    )

    assert response.status_code == 200
    assert not CreditLedgerEntry.objects.filter(organization=org).exists()


def test_credit_ledger_entry_plural_is_grammatical() -> None:
    """docs/plans/phase-8.md 8.8: Django admin's default pluralisation
    (append "s") renders "Credit ledger entrys"."""
    assert CreditLedgerEntry._meta.verbose_name_plural == "Credit ledger entries"
