"""Job / JobStep / FailedTask — schema only in Phase 1 (PRD v1.2 change 2).

No task base class, no step transitions. Behaviour is Phase 5.5.
"""

from django.db import models

from keel.core.models import OrgScopedModel, UUIDv7PrimaryKeyModel


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

    class Meta:
        indexes = (
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["organization", "status"]),
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
        indexes = (models.Index(fields=["job", "ordinal"]),)

    def __str__(self) -> str:
        return f"{self.job_id}#{self.ordinal} {self.name}"


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
