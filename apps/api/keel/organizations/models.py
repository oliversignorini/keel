"""Organisation, roles, membership, invitations (PRD §4 "Data model").

Permission *codes* and their guards belong to
``organizations/permissions.py`` (Phase 3) — this module holds data shape
only, per PRD §4 invariant 2.
"""

from django.db import models

from keel.core.models import (
    OrgScopedModel,
    SoftDeleteModel,
    TimestampedModel,
    UUIDv7PrimaryKeyModel,
)


class Organization(UUIDv7PrimaryKeyModel, TimestampedModel, SoftDeleteModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="organizations_created"
    )

    def __str__(self) -> str:
        return self.name


class Role(UUIDv7PrimaryKeyModel, TimestampedModel):
    """``organization = None`` marks a system preset (Owner/Admin/Member)."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="roles",
        db_index=True,
    )
    name = models.CharField(max_length=255)
    permissions = models.JSONField(default=list)
    is_preset = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class Membership(OrgScopedModel):
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
    )

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(fields=["organization", "user"], name="unique_org_membership"),
        )
        indexes = (models.Index(fields=["organization", "created_at"]),)

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.organization_id}"


class Invitation(OrgScopedModel):
    email = models.EmailField()
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="invitations")
    token = models.CharField(max_length=255, unique=True)
    invited_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="invitations_sent"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = (models.Index(fields=["organization", "created_at"]),)

    def __str__(self) -> str:
        return f"{self.email} -> {self.organization_id}"
