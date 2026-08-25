"""The resumable base task class (PRD §5.5.2), plus terminal status
resolution including ``partial`` and its credit settlement."""

from unittest.mock import patch

import pytest

from keel.billing.models import CreditLedgerEntry
from keel.billing.tests.factories import make_organization, make_user
from keel.jobs.models import FailedTask, Job, JobStep
from keel.jobs.registry import JobStepSpec, JobTypeSpec, registry
from keel.jobs.runner import run_job, run_job_task

pytestmark = pytest.mark.django_db


def _job(organization, type_: str, params: dict | None = None) -> Job:
    return Job.objects.create(
        organization=organization,
        type=type_,
        requested_by=make_user(),
        params=params or {},
    )


def _register(type_: str, steps) -> JobTypeSpec:
    spec = JobTypeSpec(type=type_, queue="default", credit_estimate=10, steps=steps)
    registry.register(spec)
    return spec


class _Registered:
    """Registers a job type for the duration of one test, then removes
    it — the registry is process-global, and tests must not leak types
    into each other."""

    def __init__(self, type_: str, steps) -> None:
        self.type = type_
        self.steps = steps

    def __enter__(self) -> JobTypeSpec:
        return _register(self.type, self.steps)

    def __exit__(self, *exc: object) -> None:
        del registry._specs[self.type]


def test_all_steps_succeeding_reaches_succeeded_and_records_output() -> None:
    with _Registered(
        "t.all-ok",
        (
            JobStepSpec(name="a", run=lambda ctx: "a-out"),
            JobStepSpec(name="b", run=lambda ctx: "b-out"),
        ),
    ):
        org = make_organization()
        job = _job(org, "t.all-ok")
        run_job(job.id)

    job.refresh_from_db()
    assert job.status == Job.STATUS_SUCCEEDED
    assert job.finished_at is not None
    steps = list(job.steps.order_by("ordinal"))
    assert [s.status for s in steps] == [Job.STATUS_SUCCEEDED, Job.STATUS_SUCCEEDED]
    assert steps[0].output_ref == "a-out"


def test_a_step_that_raises_fails_only_that_step() -> None:
    def _boom(ctx):
        raise ValueError("nope")

    with _Registered(
        "t.one-fails",
        (
            JobStepSpec(name="a", run=lambda ctx: "ok"),
            JobStepSpec(name="b", run=_boom),
            JobStepSpec(name="c", run=lambda ctx: "ok"),
        ),
    ):
        org = make_organization()
        job = _job(org, "t.one-fails")
        run_job(job.id)

    job.refresh_from_db()
    assert job.status == Job.STATUS_PARTIAL
    steps = list(job.steps.order_by("ordinal"))
    assert steps[0].status == Job.STATUS_SUCCEEDED
    assert steps[1].status == Job.STATUS_FAILED
    assert "nope" in steps[1].error
    assert steps[2].status == Job.STATUS_SUCCEEDED


def test_every_step_failing_reaches_failed() -> None:
    def _boom(ctx):
        raise ValueError("nope")

    with _Registered("t.all-fail", (JobStepSpec(name="a", run=_boom),)):
        org = make_organization()
        job = _job(org, "t.all-fail")
        run_job(job.id)

    job.refresh_from_db()
    assert job.status == Job.STATUS_FAILED


def test_resuming_a_job_after_a_simulated_worker_kill_skips_completed_steps() -> None:
    calls: list[str] = []

    def _record(name):
        def run(ctx):
            calls.append(name)
            return name

        return run

    with _Registered(
        "t.resume",
        (
            JobStepSpec(name="a", run=_record("a")),
            JobStepSpec(name="b", run=_record("b")),
            JobStepSpec(name="c", run=_record("c")),
        ),
    ):
        org = make_organization()
        job = _job(org, "t.resume")

        # First run "crashes" after step a: simulate by pre-creating the
        # succeeded row for "a" only and a "running" row for "b" that a
        # real crash would have left behind mid-step, then calling
        # run_job again exactly as a restarted worker would.
        JobStep.objects.create(
            job=job, ordinal=0, name="a", status=Job.STATUS_SUCCEEDED, output_ref="a"
        )
        JobStep.objects.create(job=job, ordinal=1, name="b", status=Job.STATUS_RUNNING)
        job.status = Job.STATUS_RUNNING
        job.save(update_fields=["status"])

        run_job(job.id)

    # "a" was never re-run (its step function wasn't called again); "b"
    # (left mid-flight by the "crash") and "c" ran exactly once each.
    assert calls == ["b", "c"]
    job.refresh_from_db()
    assert job.status == Job.STATUS_SUCCEEDED


def test_partial_success_releases_the_unused_portion_of_the_hold(settings) -> None:
    settings.BILLING_CREDITS = True

    def _boom(ctx):
        raise ValueError("nope")

    with _Registered(
        "t.partial-credits",
        (JobStepSpec(name="a", run=lambda ctx: "ok"), JobStepSpec(name="b", run=_boom)),
    ) as spec:
        org = make_organization()
        job = _job(org, "t.partial-credits")
        from keel.billing import credits

        credits.grant(org, 100)
        credits.hold(org, spec.credit_estimate, job=job, actor=job.requested_by)

        run_job(job.id)

    job.refresh_from_db()
    assert job.status == Job.STATUS_PARTIAL
    # 1 of 2 steps succeeded -> half the 10-credit hold (5) consumed,
    # 5 released back.
    assert credits.get_balance(org) == 100 - 5
    assert CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_RELEASE).exists()


def test_a_fully_failed_job_refunds_the_whole_hold(settings) -> None:
    settings.BILLING_CREDITS = True

    def _boom(ctx):
        raise ValueError("nope")

    with _Registered("t.fail-credits", (JobStepSpec(name="a", run=_boom),)) as spec:
        org = make_organization()
        job = _job(org, "t.fail-credits")
        from keel.billing import credits

        credits.grant(org, 100)
        credits.hold(org, spec.credit_estimate, job=job, actor=job.requested_by)

        run_job(job.id)

    assert credits.get_balance(org) == 100
    assert CreditLedgerEntry.objects.filter(job=job, kind=CreditLedgerEntry.KIND_REFUND).exists()


def test_run_job_task_dead_letters_after_exhausting_retries(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False

    with _Registered("t.task-fails", (JobStepSpec(name="a", run=lambda ctx: "ok"),)):
        org = make_organization()
        job = _job(org, "t.task-fails")

        with (
            patch("keel.jobs.runner.run_job", side_effect=RuntimeError("boom")),
            patch("keel.jobs.runner._backoff_seconds", return_value=0),
        ):
            run_job_task.delay(str(job.id))

    failed = FailedTask.objects.get()
    assert failed.task_name == "keel.jobs.runner.run_job_task"
    assert "boom" in failed.error


def test_a_saturated_organization_retries_without_dead_lettering(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False

    with _Registered("t.busy-org", (JobStepSpec(name="a", run=lambda ctx: "ok"),)):
        org = make_organization()
        job = _job(org, "t.busy-org")

        # Refused twice, then a slot frees up. Celery's eager mode
        # retries inline (no real sleep) — see
        # keel/core/tests/test_tasks_retry.py's `flaky` test for the
        # same pattern against the shim — so this completes in-process.
        acquisitions = iter([False, False, True])
        with patch(
            "keel.jobs.concurrency.OrgConcurrencyLimiter.try_acquire",
            side_effect=lambda *a, **k: next(acquisitions),
        ):
            run_job_task.delay(str(job.id))

    job.refresh_from_db()
    assert job.status == Job.STATUS_SUCCEEDED
    assert FailedTask.objects.count() == 0
