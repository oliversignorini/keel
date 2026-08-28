"""Widget — data shape only (PRD §4 "Data model"; CLAUDE.md's
per-app file shape). No queries and no business rules: reads live in
``selectors.py``, writes in ``services.py``.

Constraints, extra indexes, nullability and every other ``Meta`` option
are judgement rather than mechanics, and the generator deliberately stops
short of them (ADR 0004, "Full codegen, delete the commands"). Add them
here and write the migration with ``makemigrations``.
"""

from django.db import models

from keel.core.models import OrgScopedModel


class Widget(OrgScopedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("active", "Active"),
        ("paused", "Paused"),
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, blank=True, default="")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="widgets_created"
    )

    class Meta:
        indexes = (models.Index(fields=["organization", "created_at"]),)

    def __str__(self) -> str:
        return self.name
