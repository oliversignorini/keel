"""Reads (PRD §7's audit endpoint; docs/plans/phase-8.md 8.2). Services
mutate and return; this module queries and returns."""

from django.db.models import QuerySet

from keel.audit.models import AuditLog
from keel.organizations.models import Organization


def list_audit_logs_for_organization(organization: Organization) -> QuerySet[AuditLog]:
    return AuditLog.objects.filter(organization=organization).select_related(
        "actor", "impersonator"
    )
