"""``billing/credits.py`` — the credit ledger arithmetic (PRD §4 "Credits
— the metered-billing primitive"). Gated at 100% coverage (PRD invariant
7): this module is pure arithmetic over
rows, and if it were doing more than that, it would be too hard to reach
100% honestly.

``CreditLedgerEntry`` (append-only, never UPDATEd or DELETEd) is the
source of truth. ``CreditBalance`` is a summary index, written in the
same transaction as each entry, serialised with ``SELECT ... FOR
UPDATE`` on that row — that lock is what makes "three concurrent holds
against a balance sufficient for two" resolve to exactly two holds and
one 402 instead of a double-spend.

Two debit shapes:

- ``hold`` / ``release`` / ``refund`` — the two-phase reservation a job
  uses. ``hold`` reserves the estimated cost before work starts, so two
  browser tabs can't both spend the same balance. The job's completion
  settles the hold with ``release`` (finished under estimate — the
  unused remainder comes back) or ``refund`` (job failed — the whole
  hold comes back).
- ``consume`` — an immediate, final debit for a cost that's known
  synchronously and doesn't need a reservation phase. Same
  affordability and daily-cap checks as ``hold``; there is nothing to
  release afterwards.

``grant`` and ``adjust`` add funds directly — a plan allowance or
purchased top-up, and an operator's reasoned, audited correction. Both
skip the affordability check that gates a debit; neither skips the
locked, same-transaction write that keeps ``CreditBalance`` in step
with the ledger.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from keel.billing.models import CreditBalance, CreditLedgerEntry
from keel.core.audit import audited
from keel.core.exceptions import PaymentRequired


def credits_enabled() -> bool:
    """``BILLING_CREDITS`` is a settings flag, off by default.
    The models and this module exist regardless of
    the flag — that is what makes enabling credits a settings change
    rather than a migration. Callers that expose credits as a feature
    (endpoints, the web meter) check this; the arithmetic itself does
    not need to."""
    return bool(getattr(settings, "BILLING_CREDITS", False))


def get_balance(organization: Any) -> int:
    """The current balance — the ``CreditBalance`` index, not a fresh
    ``SUM(amount)`` over the ledger. That reconciliation is what the
    ``rebuild_credit_balances`` management command is for."""
    row, _ = CreditBalance.objects.get_or_create(organization=organization)
    return row.balance


def _daily_cap(organization: Any) -> int | None:
    """The cap is data, not a new mechanism: a
    per-plan entitlement, read through the organisation's subscription.
    No subscription, or no cap configured, means unlimited."""
    subscription = getattr(organization, "subscription", None)
    if subscription is None:
        return None
    cap = subscription.plan.entitlements.get("daily_credit_cap")
    return None if cap is None else int(cap)


def _spent_today(organization: Any) -> int:
    """A query over the ledger, not a new column: today's holds and
    immediate consumption, as a positive number of
    credits."""
    since = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total = (
        CreditLedgerEntry.objects.filter(
            organization=organization,
            kind__in=(CreditLedgerEntry.KIND_HOLD, CreditLedgerEntry.KIND_CONSUME),
            created_at__gte=since,
        ).aggregate(total=models.Sum("amount"))["total"]
        or 0
    )
    return -total


def _check_daily_cap(organization: Any, amount: int) -> None:
    cap = _daily_cap(organization)
    if cap is None:
        return
    spent = _spent_today(organization)
    if spent + amount > cap:
        raise PaymentRequired(
            code="daily_cap_exceeded",
            message="This would exceed the organisation's daily credit cap.",
            details={"cap": cap, "spent": spent, "amount": amount},
        )


def estimate(organization: Any, amount: int) -> dict[str, Any]:
    """A dry run, no writes: would ``amount`` fit under the current
    balance and the daily cap? This is what the web credit meter's
    pre-flight check calls before showing the confirm dialog."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    balance = get_balance(organization)
    cap = _daily_cap(organization)
    spent_today = _spent_today(organization)
    within_cap = cap is None or spent_today + amount <= cap
    return {
        "balance": balance,
        "amount": amount,
        "cap": cap,
        "spent_today": spent_today,
        "sufficient": balance >= amount and within_cap,
    }


def _debit(
    organization: Any,
    amount: int,
    kind: str,
    *,
    job: Any = None,
    actor: Any = None,
) -> CreditLedgerEntry:
    if amount <= 0:
        raise ValueError("amount must be positive")
    with transaction.atomic():
        balance_row, _ = CreditBalance.objects.select_for_update().get_or_create(
            organization=organization
        )
        _check_daily_cap(organization, amount)
        if balance_row.balance < amount:
            raise PaymentRequired(
                code="insufficient_credits",
                message="Insufficient credit balance.",
                details={"balance": balance_row.balance, "amount": amount},
            )
        entry = CreditLedgerEntry.objects.create(
            organization=organization,
            job=job,
            kind=kind,
            amount=-amount,
            actor=actor,
        )
        balance_row.balance -= amount
        balance_row.save(update_fields=["balance", "updated_at"])
        return entry


def hold(
    organization: Any, amount: int, *, job: Any = None, actor: Any = None
) -> CreditLedgerEntry:
    """Reserve ``amount`` for a job about to start. The row that makes
    the ledger a reservation system rather than a rollup — serialised
    against every other hold on this organisation by the
    ``SELECT ... FOR UPDATE`` on ``CreditBalance``."""
    return _debit(organization, amount, CreditLedgerEntry.KIND_HOLD, job=job, actor=actor)


def consume(
    organization: Any, amount: int, *, job: Any = None, actor: Any = None
) -> CreditLedgerEntry:
    """An immediate, final debit for a cost known synchronously — no
    prior hold, so nothing is released afterwards."""
    return _debit(organization, amount, CreditLedgerEntry.KIND_CONSUME, job=job, actor=actor)


def _credit(
    organization: Any,
    amount: int,
    kind: str,
    *,
    job: Any = None,
    actor: Any = None,
    reason: str = "",
) -> CreditLedgerEntry:
    if amount <= 0:
        raise ValueError("amount must be positive")
    with transaction.atomic():
        balance_row, _ = CreditBalance.objects.select_for_update().get_or_create(
            organization=organization
        )
        entry = CreditLedgerEntry.objects.create(
            organization=organization,
            job=job,
            kind=kind,
            amount=amount,
            actor=actor,
            reason=reason,
        )
        balance_row.balance += amount
        balance_row.save(update_fields=["balance", "updated_at"])
        return entry


def release(
    organization: Any, hold_entry: CreditLedgerEntry, amount: int, *, actor: Any = None
) -> CreditLedgerEntry:
    """A job finishing under estimate releases the unused remainder of
    its hold. ``amount`` must not exceed what the hold
    reserved — a hold's held amount is a hard cap on what can come back
    from it."""
    held = -hold_entry.amount
    if amount <= 0 or amount > held:
        raise ValueError("release amount must be positive and at most the held amount")
    return _credit(
        organization, amount, CreditLedgerEntry.KIND_RELEASE, job=hold_entry.job, actor=actor
    )


def refund(
    organization: Any, hold_entry: CreditLedgerEntry, *, actor: Any = None
) -> CreditLedgerEntry:
    """A failed job's hold is fully refunded — the
    entire held amount comes back in one entry."""
    held = -hold_entry.amount
    return _credit(
        organization, held, CreditLedgerEntry.KIND_REFUND, job=hold_entry.job, actor=actor
    )


def grant(
    organization: Any, amount: int, *, reason: str = "", actor: Any = None
) -> CreditLedgerEntry:
    """A plan allowance or a purchased top-up."""
    return _credit(organization, amount, CreditLedgerEntry.KIND_GRANT, actor=actor, reason=reason)


@audited("credits.adjustment")
def adjust(organization: Any, amount: int, *, reason: str, actor: Any) -> CreditLedgerEntry:
    """An operator correction. Never an ``UPDATE``
    against the balance — an append-only row with a reason and an
    actor, visible in Django admin and, via ``set_recorder``, in the
    audit log via ``@audited``. ``amount`` may
    be negative (a clawback) or positive (a goodwill credit); zero and
    a blank reason are both rejected so every adjustment is explicit.

    A clawback cannot take the balance below zero (ddia#5/#23): this
    used to have no floor at all, unlike every other debit path in this
    module (``_debit``'s affordability check) — the database's
    ``CHECK (balance >= 0)`` would have caught it as an ``IntegrityError``
    with no ``details`` for the caller to act on, so the check is made
    here instead, as the same ``PaymentRequired`` shape every other
    over-limit operation raises."""
    if amount == 0:
        raise ValueError("adjustment amount must be non-zero")
    if not reason:
        raise ValueError("adjustment requires a reason")
    with transaction.atomic():
        balance_row, _ = CreditBalance.objects.select_for_update().get_or_create(
            organization=organization
        )
        new_balance = balance_row.balance + amount
        if new_balance < 0:
            raise PaymentRequired(
                code="adjustment_exceeds_balance",
                message="This adjustment would take the balance below zero.",
                details={"balance": balance_row.balance, "amount": amount},
            )
        entry = CreditLedgerEntry.objects.create(
            organization=organization,
            kind=CreditLedgerEntry.KIND_ADJUSTMENT,
            amount=amount,
            actor=actor,
            reason=reason,
        )
        balance_row.balance = new_balance
        balance_row.save(update_fields=["balance", "updated_at"])
        return entry
