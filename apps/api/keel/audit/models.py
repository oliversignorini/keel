"""AuditLog (PRD §4 "Data model"). organization and actor are both
nullable — some entries are system actions with no org or no user in the
loop; impersonator is nullable and unread until Phase 8."""

from django.db import models

from keel.core.models import UUIDv7PrimaryKeyModel


class AuditLog(UUIDv7PrimaryKeyModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        db_index=True,
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    impersonator = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs_as_impersonator",
    )
    action = models.CharField(max_length=255)
    target_type = models.CharField(max_length=255, blank=True, default="")
    target_id = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = (
            models.Index(fields=["organization", "created_at"]),
            # ``GET .../audit/`` pages on ``ordering=("-id",)`` (ddia#18 —
            # id is UUIDv7, monotonic and already unique, unlike
            # created_at), not on created_at — this index backs that
            # cursor query; the created_at one above backs nothing it
            # currently pages on but is left in place for any future
            # date-range read.
            models.Index(fields=["organization", "id"]),
        )

    def __str__(self) -> str:
        return self.action
