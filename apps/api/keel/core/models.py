"""Base models and querysets every app builds on (PRD §4, "Data model").

``OrgScopedModel.organization`` points at ``"organizations.Organization"``
by string reference rather than an import — the same trick Django's own
``AUTH_USER_MODEL`` uses — so this module never imports ``keel.organizations``
and the Phase 0 import-linter contract stays green (PRD §4 invariant 2).
"""

from django.db import models

from keel.core.ids import uuid7


class UUIDv7PrimaryKeyField(models.UUIDField):
    """A UUID primary key field defaulting to :func:`keel.core.ids.uuid7`."""

    def __init__(self, **kwargs: object) -> None:
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


class SoftDeleteModel(models.Model):
    """Abstract mixin for the few tables that need a soft-delete marker.

    Not a general convention — added only where the data model actually
    calls for it (``Organization.deleted_at``, per PRD §4 task 1.3).
    """

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
