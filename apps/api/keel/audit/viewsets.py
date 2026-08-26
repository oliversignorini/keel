"""``GET /api/v1/organizations/<org_slug>/audit/`` (PRD §7; docs/plans/
phase-8.md 8.2). Read-only, behind ``audit.view``, cursor-paginated —
inherits ``OrgScopedViewSet``'s default ``CursorPagination`` (PRD §7
conventions). Keeps the existing URL shape: the rename to
``/api/v1/orgs/`` is the conformance pass immediately after this phase,
not this one (docs/plans/phase-8.md's boundary table).

``RetrieveModelMixin`` is included even though the audit settings page
only lists — an ``OrgScopedViewSet`` with no detail route can't be
walked by the tenant-isolation meta-test (``assert_cross_org_404`` calls
``retrieve``), and an audit trail leaking across organisations is
exactly the kind of gap PRD §4 invariant 7 exists to catch."""

from typing import Any

from rest_framework import mixins

from keel.audit import selectors
from keel.audit.serializers import AuditLogSerializer
from keel.core.authz import OrgScopedViewSet
from keel.organizations.permissions import Perm


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, OrgScopedViewSet):
    serializer_class = AuditLogSerializer
    organization_scoped = True
    test_factory = "keel.audit.tests.factories.audit_log_factory"
    required_permissions: tuple[str, ...] = (Perm.AUDIT_VIEW,)

    def get_queryset(self) -> Any:
        return selectors.list_audit_logs_for_organization(self.organization)
