"""Row builder for ``AuditLogResource.test_factory`` (PRD §4 invariant 7 —
the cross-org meta-test walk)."""

from django.utils.crypto import get_random_string

from keel.accounts.models import User
from keel.audit.models import AuditLog
from keel.organizations.models import Organization


def audit_log_factory(organization: Organization) -> AuditLog:
    actor = User.objects.create_user(
        email=f"audit-{organization.pk}-{get_random_string(6).lower()}@example.com",
        password="s3cret-pass",
    )
    return AuditLog.objects.create(
        organization=organization, actor=actor, action="widget.created", target_type="Widget"
    )
