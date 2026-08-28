"""Base models and querysets every app builds on (PRD §4, "Data model").

``OrgScopedModel.organization`` points at ``"organizations.Organization"``
by string reference rather than an import — the same trick Django's own
``AUTH_USER_MODEL`` uses — so this module never imports ``keel.organizations``
and the import-linter contract stays green (PRD §4 invariant 2).
"""

from typing import Any

from django.db import models

from keel.core.ids import uuid7


class UUIDv7PrimaryKeyField(models.UUIDField):
    """A UUID primary key field defaulting to :func:`keel.core.ids.uuid7`."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("primary_key", True)
        kwargs.setdefault("default", uuid7)
        kwargs.setdefault("editable", False)
        super().__init__(**kwargs)


class UUIDv7PrimaryKeyModel(models.Model):
    """Abstract mixin giving a model a UUIDv7 primary key named ``id``."""

    id = UUIDv7PrimaryKeyField()

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    """Abstract mixin adding ``created_at`` / ``updated_at``."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OrgScopedQuerySet(models.QuerySet):
    def for_organization(self, organization: models.Model) -> "OrgScopedQuerySet":
        return self.filter(organization=organization)


class OrgScopedModel(UUIDv7PrimaryKeyModel, TimestampedModel):
    """Abstract base for every tenant-scoped table.

    Concrete subclasses are indexed on ``organization`` by default; add
    ``(organization, created_at)`` explicitly on tables the router
    cursor-paginates (PRD §4, "Data model").
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        db_index=True,
    )

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        abstract = True


class ProvenanceMixin(models.Model):
    """Nullable link from a produced record back to the job run and the
    input that produced it.

    Future document-ingestion work needs to answer "what produced this
    row, from what input, by which job run" — this is the smallest thing
    that answers it: two columns, no behaviour, string-referenced onto
    ``jobs.Job`` the same way ``OrgScopedModel.organization`` string-refs
    ``organizations.Organization`` above, so any app's model can inherit
    this mixin without ever importing ``keel.jobs`` (PRD §4 invariant 2)
    and without ``keel.jobs`` knowing a single one of its consumers
    exists. ``keel/jobs/models.py::JobArtifact`` demonstrates the shape
    against the demo job; a real ingestion pipeline (not built here) would
    add this mixin to whatever model it produces rows into
    and set the two fields from inside its own job steps."""

    produced_by_job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    produced_by_input_ref = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Opaque description of the specific input this row was derived from "
        "(a source row's id, a file key, a params field) — free-form because what "
        "counts as 'the input' is a consumer decision, not this mixin's.",
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Abstract mixin for the few tables that need a soft-delete marker.

    Not a general convention — added only where the data model actually
    calls for it (``Organization.deleted_at``, per PRD §4 task 1.3).
    """

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
