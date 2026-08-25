"""FileUpload (PRD §4 "Data model"). Presigned direct upload from the
browser to R2; Django issues the signature and records this row."""

from django.db import models

from keel.core.models import OrgScopedModel


class FileUpload(OrgScopedModel):
    STATUS_PENDING = "pending"
    STATUS_COMPLETE = "complete"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETE, "Complete"),
    )

    uploader = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="file_uploads"
    )
    key = models.CharField(max_length=1024, unique=True)
    content_type = models.CharField(max_length=255)
    size = models.BigIntegerField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)

    class Meta:
        indexes = (models.Index(fields=["organization", "created_at"]),)

    def __str__(self) -> str:
        return self.key
