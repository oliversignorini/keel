"""The named acceptance criterion: "three
concurrent holds against a balance sufficient for two produce exactly
two holds and one 402." Run against a real Postgres with real threads —
not mocked locking, which would prove nothing about the
``SELECT ... FOR UPDATE`` that actually serialises this.

``transaction=True`` is required so each thread's ``hold()`` really
commits and really blocks on the row lock the other threads are holding,
instead of running inside pytest-django's default per-test transaction
(which never lets a second connection see the first connection's
uncommitted row lock the way Postgres does across genuinely separate
connections).
"""

import threading

import pytest
from django.db import connection

from keel.billing import credits
from keel.billing.models import CreditBalance
from keel.billing.tests.factories import make_organization
from keel.core.exceptions import PaymentRequired


@pytest.mark.django_db(transaction=True)
def test_three_concurrent_holds_against_a_balance_for_two_yield_one_402():
    org = make_organization()
    credits.grant(org, 20)  # enough for exactly two holds of 10, not three

    outcomes: list[str] = []
    outcomes_lock = threading.Lock()
    barrier = threading.Barrier(3)

    def attempt() -> None:
        try:
            barrier.wait(timeout=5)
            try:
                credits.hold(org, 10)
                outcome = "ok"
            except PaymentRequired:
                outcome = "402"
        finally:
            connection.close()
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert outcomes.count("ok") == 2
    assert outcomes.count("402") == 1
    assert len(outcomes) == 3

    balance_row = CreditBalance.objects.get(organization=org)
    assert balance_row.balance == 0
