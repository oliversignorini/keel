"""Third-party OAuth connections (PRD §4, "Third-party OAuth connections").

Distinct from allauth's ``SocialAccount``: organisation-scoped, not
user-scoped, and tokens are encrypted at rest via ``keel/core/crypto.py``.
Admin registration excludes both token fields entirely — see
``keel/connections/admin.py``.
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from keel.core.models import OrgScopedModel


class Connection(OrgScopedModel):
    STATUS_ACTIVE = "active"
    STATUS_REAUTH_REQUIRED = "reauth_required"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_REAUTH_REQUIRED, "Re-authorisation required"),
        (STATUS_REVOKED, "Revoked"),
    )

    provider = models.CharField(max_length=100)
    external_account = models.CharField(max_length=255)
    access_token = models.TextField()
    refresh_token = models.TextField()
    scopes = ArrayField(models.CharField(max_length=255), default=list)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    connected_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="connections"
    )
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["organization", "provider", "external_account"],
                name="unique_org_provider_account",
            ),
        )
        indexes = (models.Index(fields=["organization", "created_at"]),)

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_account} @ {self.organization_id}"
