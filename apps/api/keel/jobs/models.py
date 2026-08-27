"""Job / JobStep / FailedTask — schema only in Phase 1 (PRD v1.2 change 2).

No task base class, no step transitions. Behaviour is Phase 5.5.
"""

from django.db import models
from django.db.models import Q

from keel.core.models import OrgScopedModel, ProvenanceMixin, UUIDv7PrimaryKeyModel


class Job(OrgScopedModel):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    )

    type = models.CharField(max_length=100)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="jobs_requested"
    )
    params = models.JSONField(default=dict)
    result_ref = models.CharField(max_length=255, blank=True, default="")
    error = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # Pinned at creation from the registry's step list (ddia#24) — the
    # runner totals against this column, never the live registry, so
    # re-registering `type` with a different step count never re-prices
    # a job already in flight. Nullable only for rows written before this
    # column existed; every row created through create_job sets it.
    step_count = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = (
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["organization", "status"]),
        )
        constraints = (
            # ddia#11: the real uniqueness guarantee — select_for_update
            # in keel.jobs.services.create_job and the cache claim in
            # keel.core.idempotency both narrow the race window but
            # neither is a substitute for this. Empty keys are excluded:
            # "" means "no idempotency key was supplied", and every job
            # created without one must not collide with every other.
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="unique_org_idempotency_key",
            ),
        )

    def __str__(self) -> str:
        return f"{self.type} ({self.status})"


class JobStep(UUIDv7PrimaryKeyModel):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="steps")
    name = models.CharField(max_length=255)
    ordinal = models.IntegerField()
    status = models.CharField(max_length=16, default=Job.STATUS_QUEUED)
    output_ref = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        constraints = (
            # ddia#12: an index alone doesn't stop two runners on the same
            # job (a duplicate delivery, a manual re-drive) from both
            # get_or_create-ing ordinal 0 and forking the step set that
            # _settle_credits' proportional cost is computed against.
            models.UniqueConstraint(fields=["job", "ordinal"], name="unique_job_step_ordinal"),
        )

    def __str__(self) -> str:
        return f"{self.job_id}#{self.ordinal} {self.name}"


class JobArtifact(OrgScopedModel, ProvenanceMixin):
    """Demo-only scaffolding (mirrors ``keel/widgets/`` — same removal
    note as ``keel/jobs/demo.py``, which is what writes to this table):
    demonstrates ``ProvenanceMixin`` against a real, migrated model rather
    than only describing it in a docstring. The demo job's ``count`` step
    writes one row here per run, carrying ``produced_by_job`` (the job
    that ran it) and ``produced_by_input_ref`` (a description of the
    params it counted) — see ``keel.jobs.demo``."""

    kind = models.CharField(max_length=100)
    value = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"{self.kind} ({self.pk})"


class FailedTask(UUIDv7PrimaryKeyModel):
    task_name = models.CharField(max_length=255)
    args = models.JSONField(default=dict)
    error = models.TextField(blank=True, default="")
    traceback = models.TextField(blank=True, default="")
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    redriven_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.task_name
