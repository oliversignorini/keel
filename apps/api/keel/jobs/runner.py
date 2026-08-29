"""The resumable base task class (PRD §5.5.2) — Tier 2, used directly
against Celery per PRD invariant 5
rather than through ``keel/core/tasks.py``'s Tier 1 shim: step-level
commits, resumption, and per-organisation fairness are exactly the
surface that shim exists to *not* cover.

``run_job`` is the resumable core, deliberately a plain function rather
than a method on a custom ``Task`` subclass — it takes only a job id
(PRD §5 "every task takes IDs, never model instances") and is safe to
call twice on the same job: each step commits its own transition before
the next step starts, so a worker killed mid-job leaves exactly the
in-flight step not yet marked ``succeeded``, and a re-run skips every
step that already is one and resumes at that one.

``run_job_task`` wraps it as the actual Celery task: per-organisation
concurrency backpressure (retry without blocking the worker, so a
saturated organisation never holds up another one's job — see
``keel/jobs/concurrency.py``) and the retry/dead-letter policy, mirrored
from the shim's rather than imported from it, since PRD invariant 5 is
explicit that the shim itself must not grow to cover this.
"""

from __future__ import annotations

import logging
import random
import traceback as traceback_module
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from keel.billing import credits
from keel.core.tasks import report_to_sentry
from keel.jobs.concurrency import OrgConcurrencyLimiter
from keel.jobs.models import FailedTask, Job, JobStep
from keel.jobs.pubsub import publish_job_event, publish_step_event
from keel.jobs.registry import StepContext, registry

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 5
JITTER_FRACTION = 0.25
CONCURRENCY_RETRY_SECONDS = 5
STUCK_JOB_THRESHOLD_MINUTES = 60


def _backoff_seconds(retries: int) -> float:
    base = float(BASE_BACKOFF_SECONDS * (2**retries))
    return base + random.uniform(0, base * JITTER_FRACTION)


def locked_hold_entry(job: Job) -> Any:
    """The job's most recent hold entry, locked with ``SELECT ... FOR
    UPDATE``. Callers that settle a hold (``_settle_credits``,
    ``keel.jobs.services.cancel_job``) must take this lock *before*
    checking whether the hold is already settled — otherwise two
    concurrent settlement attempts (a retried delivery and a cancel, or
    two retried deliveries) both read "not yet settled" and both write.
    Migration-free stand-in for a ``settles`` FK plus a unique
    constraint: there is no row to key uniqueness off, so the
    lock on the hold itself is what serialises the check."""
    from keel.billing.models import CreditLedgerEntry

    return (
        CreditLedgerEntry.objects.select_for_update()
        .filter(job=job, kind=CreditLedgerEntry.KIND_HOLD)
        .order_by("-created_at")
        .first()
    )


def hold_already_settled(job: Job) -> bool:
    """Whether a ``release`` or ``refund`` entry already exists for
    ``job`` — the settlement has no operation id of its own. Must only be
    called while ``locked_hold_entry`` holds its lock, inside the same
    transaction."""
    from keel.billing.models import CreditLedgerEntry

    return CreditLedgerEntry.objects.filter(
        job=job, kind__in=(CreditLedgerEntry.KIND_RELEASE, CreditLedgerEntry.KIND_REFUND)
    ).exists()


def _settle_credits(job: Job, succeeded: int, total: int) -> None:
    """Consumes the proportion of the hold the job actually used and
    releases the rest (PRD §5.5.2: "a job that succeeds on 8 of 10 items
    surfaces its results and releases the unused credit hold"). A job
    that fails outright (no step succeeded) is a full refund rather than
    a release — nothing was delivered.

    Idempotent by lock-and-check: the hold row is locked before
    settlement is decided, and a hold that already has a release/refund
    entry against it is left alone — a re-delivered ``run_job`` call
    settles at most once."""
    if not credits.credits_enabled():
        return

    with transaction.atomic():
        hold_entry = locked_hold_entry(job)
        if hold_entry is None or hold_already_settled(job):
            return
        held = -hold_entry.amount
        if succeeded == 0:
            credits.refund(job.organization, hold_entry, actor=job.requested_by)
            return
        actual_cost = round(held * succeeded / total)
        unused = held - actual_cost
        if unused > 0:
            credits.release(job.organization, hold_entry, unused, actor=job.requested_by)


def run_job(job_id: Any) -> None:
    job = Job.objects.select_related("organization").get(pk=job_id)
    spec = registry.get(job.type)
    limiter = OrgConcurrencyLimiter()

    if job.status == Job.STATUS_QUEUED:
        job.status = Job.STATUS_RUNNING
        job.started_at = job.started_at or timezone.now()
        job.save(update_fields=["status", "started_at"])
        publish_job_event(job)

    results: dict[str, Any] = {}
    succeeded = 0
    # Pinned at creation, not the live registry's step count —
    # a job created before `type` was re-registered with a different step
    # list must still total against the count it was actually held
    # credits for. Falls back to the registry for rows written before
    # this column existed (job.step_count is nullable).
    total = job.step_count if job.step_count is not None else len(spec.steps)

    for ordinal, step_spec in enumerate(spec.steps):
        job.refresh_from_db(fields=["status", "error"])
        if job.status == Job.STATUS_FAILED and job.error == "cancelled":
            # A cancel request (keel.jobs.services.cancel_job) landed
            # while this task was running. It already settled credits
            # and published the terminal event — stop before the next
            # step rather than resuming or overwriting its outcome.
            return

        # Step-boundary heartbeat: the concurrency slot this
        # job holds (acquired by run_job_task before run_job was called)
        # has a 1-hour lease with no renewal otherwise — any job whose
        # steps together take longer than that silently loses its slot
        # partway through, over-admitting the organisation for the rest
        # of the run. Renewing here costs one Redis round trip per step.
        limiter.renew(job.organization_id, job.id)

        step, _created = JobStep.objects.get_or_create(
            job=job,
            ordinal=ordinal,
            defaults={"name": step_spec.name, "status": Job.STATUS_QUEUED},
        )

        if step.status == Job.STATUS_SUCCEEDED:
            succeeded += 1
            results[step.name] = step.output_ref
            continue
        if step.status == Job.STATUS_FAILED:
            continue

        step.status = Job.STATUS_RUNNING
        step.started_at = step.started_at or timezone.now()
        step.save(update_fields=["status", "started_at"])
        publish_step_event(job, step)

        context = StepContext(
            job_id=job.id,
            organization_id=job.organization_id,
            params=job.params,
            results=results,
        )
        try:
            with transaction.atomic():
                output = step_spec.run(context)
                step.status = Job.STATUS_SUCCEEDED
                step.output_ref = "" if output is None else str(output)
                step.finished_at = timezone.now()
                step.save(update_fields=["status", "output_ref", "finished_at"])
            succeeded += 1
            results[step.name] = step.output_ref
        except Exception as exc:
            step.status = Job.STATUS_FAILED
            step.error = str(exc)
            step.finished_at = timezone.now()
            step.save(update_fields=["status", "error", "finished_at"])
        publish_step_event(job, step)

    if succeeded == total:
        final_status = Job.STATUS_SUCCEEDED
    elif succeeded == 0:
        final_status = Job.STATUS_FAILED
    else:
        final_status = Job.STATUS_PARTIAL

    # Guarded compare-and-set: if a concurrent cancel_job already
    # moved this job out of RUNNING (e.g. a cancel landing on the final
    # step), this update matches zero rows and settlement is skipped
    # entirely — cancel_job already refunded the hold, so this loop must
    # not also release/refund it.
    updated = Job.objects.filter(pk=job.pk, status=Job.STATUS_RUNNING).update(
        status=final_status, finished_at=timezone.now()
    )
    job.refresh_from_db()
    if updated:
        _settle_credits(job, succeeded, total)
    publish_job_event(job)


def _dead_letter(task_name: str, job_id: Any, exc: Exception) -> None:
    traceback_text = "".join(traceback_module.format_exception(type(exc), exc, exc.__traceback__))
    FailedTask.objects.create(
        task_name=task_name,
        args={"args": [str(job_id)], "kwargs": {}},
        error=str(exc),
        traceback=traceback_text,
        attempts=MAX_RETRIES,
    )
    # docs/boundary-guardrails.md "Async boundary": mirrors the Tier-1
    # shim's dead-letter policy (keel/core/tasks.py) — a FailedTask row
    # alone is invisible until someone thinks to look at the admin;
    # Sentry is what actually pages on-call.
    report_to_sentry(task_name, str(exc), traceback_text, exc=exc)
    logger.error("job %s dead-lettered after %s attempts", job_id, MAX_RETRIES)


@shared_task(bind=True, name="keel.jobs.runner.run_job_task", max_retries=MAX_RETRIES)
def run_job_task(self: Any, job_id: Any) -> None:
    job = Job.objects.select_related("organization").get(pk=job_id)
    limiter = OrgConcurrencyLimiter()
    if not limiter.try_acquire(job.organization_id, job.id):
        # Unbounded retry count for backpressure alone — this must never
        # dead-letter a job just because its organisation was busy. Only
        # a real step/task failure below counts against MAX_RETRIES.
        raise self.retry(countdown=CONCURRENCY_RETRY_SECONDS, max_retries=None)
    try:
        run_job(job_id)
    except Exception as exc:
        if self.request.retries >= MAX_RETRIES:
            _dead_letter(self.name, job_id, exc)
            return
        raise self.retry(exc=exc, countdown=_backoff_seconds(self.request.retries)) from exc
    finally:
        limiter.release(job.organization_id, job.id)


def sweep_stuck_jobs(*, threshold_minutes: int = STUCK_JOB_THRESHOLD_MINUTES) -> int:
    """Beat sweeper: ``task_acks_late`` means a worker killed
    mid-job re-delivers the message and ``run_job`` resumes correctly —
    but a worker that hangs, or is killed *after* the broker's ack, never
    gets a re-delivery, and the ``Job`` row is then stuck in ``running``
    forever holding its credit hold. Fails any job whose ``started_at``
    is older than ``threshold_minutes`` and refunds its hold; a job that
    settles or resumes normally in the meantime is skipped by the same
    guarded update ``run_job`` itself uses."""
    cutoff = timezone.now() - timedelta(minutes=threshold_minutes)
    stuck_ids = list(
        Job.objects.filter(status=Job.STATUS_RUNNING, started_at__lt=cutoff).values_list(
            "pk", flat=True
        )
    )
    swept = 0
    for job_id in stuck_ids:
        updated = Job.objects.filter(pk=job_id, status=Job.STATUS_RUNNING).update(
            status=Job.STATUS_FAILED, error="stuck", finished_at=timezone.now()
        )
        if not updated:
            continue
        job = Job.objects.select_related("organization").get(pk=job_id)
        if credits.credits_enabled():
            with transaction.atomic():
                hold_entry = locked_hold_entry(job)
                if hold_entry is not None and not hold_already_settled(job):
                    credits.refund(job.organization, hold_entry, actor=job.requested_by)
        publish_job_event(job)
        swept += 1
    return swept


@shared_task(name="keel.jobs.runner.sweep_stuck_jobs_task")
def sweep_stuck_jobs_task() -> int:
    return sweep_stuck_jobs()
