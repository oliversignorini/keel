"""Settlement must be idempotent under re-delivery, and
these tests are the guard for that — each calls a supposedly-idempotent
function twice (or races cancel against completion) and asserts the
ledger and job state are identical to a single call, with no broker and
no real concurrency required."""

from datetime import timedelta

import pytest
from django.utils import timezone

from keel.billing import credits
from keel.billing.models import CreditLedgerEntry
from keel.billing.tests.factories import make_organization, make_user
from keel.jobs import services
from keel.jobs.models import Job
from keel.jobs.registry import JobStepSpec, JobTypeSpec, registry
from keel.jobs.runner import _settle_credits, run_job, sweep_stuck_jobs

pytestmark = pytest.mark.django_db


class _Registered:
    def __init__(self, type_: str, steps) -> None:
        self.type = type_
        self.steps = steps

    def __enter__(self) -> JobTypeSpec:
        spec = JobTypeSpec(type=self.type, queue="default", credit_estimate=10, steps=self.steps)
        registry.register(spec)
        return spec

    def __exit__(self, *exc: object) -> None:
        del registry._specs[self.type]


def _job(organization, type_: str) -> Job:
    return Job.objects.create(organization=organization, type=type_, requested_by=make_user())


def _ledger_snapshot(organization) -> list[tuple[str, int]]:
    return list(
        CreditLedgerEntry.objects.filter(organization=organization)
        .order_by("created_at", "pk")
        .values_list("kind", "amount")
    )


def test_run_job_called_twice_on_a_partially_succeeded_job_releases_exactly_once(settings) -> None:
    settings.BILLING_CREDITS = True

    def _boom(ctx):
        raise ValueError("nope")

    with _Registered(
        "t.idempotent-partial",
        (JobStepSpec(name="a", run=lambda ctx: "ok"), JobStepSpec(name="b", run=_boom)),
    ) as spec:
        org = make_organization()
        job = _job(org, "t.idempotent-partial")
        credits.grant(org, 100)
        credits.hold(org, spec.credit_estimate, job=job, actor=job.requested_by)

        run_job(job.id)
        balance_after_first = credits.get_balance(org)
        ledger_after_first = _ledger_snapshot(org)

        # A re-delivered task (Celery is at-least-once) re-runs run_job on
        # a job whose steps are all already terminal — it must fall
        # through the whole loop without settling a second time.
        run_job(job.id)

    assert credits.get_balance(org) == balance_after_first
    assert _ledger_snapshot(org) == ledger_after_first
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_RELEASE).count() == 1
    )


def test_run_job_called_twice_on_a_fully_failed_job_refunds_exactly_once(settings) -> None:
    settings.BILLING_CREDITS = True

    def _boom(ctx):
        raise ValueError("nope")

    with _Registered("t.idempotent-fail", (JobStepSpec(name="a", run=_boom),)) as spec:
        org = make_organization()
        job = _job(org, "t.idempotent-fail")
        credits.grant(org, 100)
        credits.hold(org, spec.credit_estimate, job=job, actor=job.requested_by)

        run_job(job.id)
        run_job(job.id)

    assert credits.get_balance(org) == 100
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_REFUND).count() == 1
    )


def test_settle_credits_called_twice_directly_settles_once(settings) -> None:
    """Exercises ``_settle_credits`` directly, bypassing ``run_job``'s own
    guard — the lock-and-check inside ``_settle_credits`` itself
    must hold even if some future caller forgets the guard."""
    settings.BILLING_CREDITS = True
    org = make_organization()
    job = _job(org, "t.direct-settle")
    credits.grant(org, 100)
    credits.hold(org, 10, job=job, actor=job.requested_by)

    _settle_credits(job, succeeded=1, total=2)
    _settle_credits(job, succeeded=1, total=2)

    assert credits.get_balance(org) == 95  # 100 - 10 held + 5 released, once
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_RELEASE).count() == 1
    )


def test_cancel_job_called_twice_refunds_exactly_once(settings) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    user = make_user()
    credits.grant(org, 100)
    job = Job.objects.create(organization=org, type="t.cancel-twice", requested_by=user)
    credits.hold(org, 3, job=job, actor=user)

    first = services.cancel_job(job=job, actor=user)
    second = services.cancel_job(job=job, actor=user)

    assert first.status == second.status == Job.STATUS_FAILED
    assert credits.get_balance(org) == 100
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_REFUND).count() == 1
    )


def test_cancel_after_run_job_already_settled_does_not_double_refund(settings) -> None:
    """cancel-vs-complete: a cancel landing after the runner
    already settled the hold (e.g. the cancel request was in flight while
    the last step finished) must not also refund it."""
    settings.BILLING_CREDITS = True
    with _Registered(
        "t.cancel-after-complete", (JobStepSpec(name="a", run=lambda ctx: "ok"),)
    ) as spec:
        org = make_organization()
        job = _job(org, "t.cancel-after-complete")
        credits.grant(org, 100)
        credits.hold(org, spec.credit_estimate, job=job, actor=job.requested_by)

        run_job(job.id)
        job.refresh_from_db()
        assert job.status == Job.STATUS_SUCCEEDED
        balance_after_run = credits.get_balance(org)

        cancelled = services.cancel_job(job=job, actor=job.requested_by)

    assert cancelled.status == Job.STATUS_SUCCEEDED  # already terminal — cancel is a no-op
    assert credits.get_balance(org) == balance_after_run
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_REFUND).count() == 0
    )


def test_run_job_skips_settlement_when_the_hold_is_already_settled(settings) -> None:
    """Belt-and-braces on top of the status-write guard: even if a job
    row is somehow found RUNNING again (a manual re-drive, a bug
    elsewhere), ``_settle_credits``'s own lock-and-check must still catch
    that the hold was already settled and refuse to settle twice."""
    settings.BILLING_CREDITS = True

    def _boom(ctx):
        raise ValueError("nope")

    with _Registered(
        "t.concurrent-terminal",
        (JobStepSpec(name="a", run=lambda ctx: "ok"), JobStepSpec(name="b", run=_boom)),
    ) as spec:
        org = make_organization()
        job = _job(org, "t.concurrent-terminal")
        credits.grant(org, 100)
        credits.hold(org, spec.credit_estimate, job=job, actor=job.requested_by)

        run_job(job.id)
        job.refresh_from_db()
        assert job.status == Job.STATUS_PARTIAL
        balance_after_first = credits.get_balance(org)

        # Simulate a cancel racing the tail of the loop: force the row
        # back to RUNNING without a fresh hold, exactly the "already
        # terminal, has already settled" state the guard must catch by
        # existing-settlement check even if the status-write guard alone
        # were bypassed.
        Job.objects.filter(pk=job.pk).update(status=Job.STATUS_RUNNING)
        run_job(job.id)

    assert credits.get_balance(org) == balance_after_first
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_RELEASE).count() == 1
    )


def test_sweep_stuck_jobs_fails_and_refunds_a_job_stuck_past_the_threshold(settings) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    user = make_user()
    credits.grant(org, 100)
    job = Job.objects.create(
        organization=org,
        type="t.stuck",
        requested_by=user,
        status=Job.STATUS_RUNNING,
        started_at=timezone.now() - timedelta(minutes=120),
    )
    credits.hold(org, 10, job=job, actor=user)

    swept = sweep_stuck_jobs(threshold_minutes=60)

    assert swept == 1
    job.refresh_from_db()
    assert job.status == Job.STATUS_FAILED
    assert job.error == "stuck"
    assert credits.get_balance(org) == 100
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_REFUND).count() == 1
    )


def test_sweep_stuck_jobs_leaves_jobs_within_the_threshold_alone(settings) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    user = make_user()
    credits.grant(org, 100)
    job = Job.objects.create(
        organization=org,
        type="t.not-stuck-yet",
        requested_by=user,
        status=Job.STATUS_RUNNING,
        started_at=timezone.now(),
    )
    credits.hold(org, 10, job=job, actor=user)

    swept = sweep_stuck_jobs(threshold_minutes=60)

    assert swept == 0
    job.refresh_from_db()
    assert job.status == Job.STATUS_RUNNING


def test_sweep_stuck_jobs_called_twice_refunds_exactly_once(settings) -> None:
    settings.BILLING_CREDITS = True
    org = make_organization()
    user = make_user()
    credits.grant(org, 100)
    job = Job.objects.create(
        organization=org,
        type="t.stuck-twice",
        requested_by=user,
        status=Job.STATUS_RUNNING,
        started_at=timezone.now() - timedelta(minutes=120),
    )
    credits.hold(org, 10, job=job, actor=user)

    first_swept = sweep_stuck_jobs(threshold_minutes=60)
    second_swept = sweep_stuck_jobs(threshold_minutes=60)

    assert first_swept == 1
    assert second_swept == 0  # already FAILED, no longer matches the RUNNING filter
    assert credits.get_balance(org) == 100
    assert (
        CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_REFUND).count() == 1
    )
