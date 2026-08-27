"""Job creation and cancellation (PRD §4 invariant 1: "services.py — ORM,
transactions, side effects, all writes"). The one place that ties the
registry, the idempotency guarantee, and the credit hold together —
job-creating POSTs go through ``create_job``, never straight to
``Job.objects.create()``.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from keel.billing import credits
from keel.core.audit import audited
from keel.core.exceptions import UnprocessableEntity
from keel.jobs.models import Job
from keel.jobs.pubsub import publish_job_event
from keel.jobs.registry import UnknownJobType, registry
from keel.jobs.runner import hold_already_settled, locked_hold_entry, run_job_task


@audited("job.created")
def create_job(
    *,
    organization: Any,
    actor: Any,
    type: str,
    params: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> Job:
    try:
        spec = registry.get(type)
    except UnknownJobType as exc:
        raise UnprocessableEntity(code="unknown_job_type", message=str(exc)) from None

    with transaction.atomic():
        if idempotency_key:
            # select_for_update serialises this against a second request
            # replaying the same key inside the same transaction window;
            # keel.jobs.idempotency's cache claim covers the same race at
            # the HTTP layer, cheaper, ahead of ever reaching here.
            existing = (
                Job.objects.select_for_update()
                .filter(organization=organization, idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None:
                return existing

        job = Job.objects.create(
            organization=organization,
            type=type,
            requested_by=actor,
            params=params or {},
            idempotency_key=idempotency_key,
        )
        if credits.credits_enabled() and spec.credit_estimate > 0:
            credits.hold(organization, spec.credit_estimate, job=job, actor=actor)

    transaction.on_commit(lambda: run_job_task.apply_async(args=[str(job.id)], queue=spec.queue))
    return job


@audited("job.cancelled")
def cancel_job(*, job: Job, actor: Any) -> Job:
    """Best-effort: a job already mid-step finishes that step (there is
    no schema-level "cancelled" status to interrupt into — ``Job``'s
    columns are fixed at the Phase 1 baseline) but stops before the
    next one — see the resumption guard at the top of
    ``keel.jobs.runner.run_job``'s per-step loop.

    Locks the ``Job`` row and re-checks terminal status inside the
    transaction (ddia#2): the caller's in-memory ``job`` may be stale, and
    without this lock two concurrent cancels of the same job — or a
    cancel racing the runner's own settlement — can both pass the
    terminal-status check and both refund the hold."""
    with transaction.atomic():
        job = Job.objects.select_for_update().select_related("organization").get(pk=job.pk)
        if job.status in (Job.STATUS_SUCCEEDED, Job.STATUS_PARTIAL, Job.STATUS_FAILED):
            return job

        job.status = Job.STATUS_FAILED
        job.error = "cancelled"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        if credits.credits_enabled():
            hold_entry = locked_hold_entry(job)
            if hold_entry is not None and not hold_already_settled(job):
                credits.refund(job.organization, hold_entry, actor=actor)

    publish_job_event(job)
    return job
