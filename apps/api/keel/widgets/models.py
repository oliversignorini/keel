"""Widget — the demo resource (PRD §4 "Data model"). The copy-paste
pattern /new-resource generates from. ``init`` deletes this app."""

from django.db import models

from keel.core.models import OrgScopedModel


class Widget(OrgScopedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=32, blank=True, default="")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="widgets_created"
    )

    class Meta:
        indexes = (models.Index(fields=["organization", "created_at"]),)

    def __str__(self) -> str:
        return self.name
