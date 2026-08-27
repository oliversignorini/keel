"""``GET /api/v1/orgs/<org_slug>/audit/`` (PRD §7; docs/plans/
phase-8.md 8.2; phase-10.md 10.C). Read-only, behind ``audit.view``,
cursor-paginated.

``AuditLogResource`` declares a ``detail_url_template`` even though the
audit settings page only lists — an ``OrgScopedResource`` with no detail
route can't be walked by the tenant-isolation meta-test, and an audit
trail leaking across organisations is exactly the kind of gap PRD §4
invariant 7 exists to catch.

``POST /api/v1/impersonation/exit/`` (PRD §6 "Impersonation") is global
and not org-scoped — the frontend `<ImpersonationBanner>`'s only action.
"""

from typing import Any

from django.http import Http404
from ninja import Status

from keel.audit import selectors
from keel.audit.models import AuditLog
from keel.audit.schemas import AuditLogOut
from keel.core.impersonation import end_impersonation, get_impersonator_id
from keel.core.ninja_authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.ninja_pagination import paginate
from keel.organizations.permissions import Perm


class AuditLogResource(OrgScopedResource):
    router = keel_router(tags=["audit"])
    organization_scoped = True
    test_factory = "keel.audit.tests.factories.audit_log_factory"
    required_permissions = (Perm.AUDIT_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/audit/{pk}/"


router = AuditLogResource.router

# Not org-scoped — a separate router mounted at the API root (config/urls.py),
# not nested under "/organizations" the way `router` above is.
impersonation_router = keel_router(tags=["impersonation"])


@router.get("/{org_slug}/audit/")
def list_audit_logs(request: Any, org_slug: str) -> dict:
    organization = resolve_and_authorize(request, org_slug, AuditLogResource.required_permissions)
    queryset = selectors.list_audit_logs_for_organization(organization)
    return paginate(request, queryset, lambda row: AuditLogOut.from_orm(row).dict())


@router.get("/{org_slug}/audit/{pk}/", response=AuditLogOut)
def retrieve_audit_log(request: Any, org_slug: str, pk: str) -> AuditLog:
    organization = resolve_and_authorize(request, org_slug, AuditLogResource.required_permissions)
    row = selectors.list_audit_logs_for_organization(organization).filter(pk=pk).first()
    if row is None:
        raise Http404
    return row


@impersonation_router.post(
    "/impersonation/exit/", response={204: None}, url_name="impersonation-exit"
)
def impersonation_exit(request: Any) -> Status[None]:
    from keel.accounts.models import User

    impersonator_id = get_impersonator_id(request)
    if impersonator_id is None:
        raise Http404
    impersonator = User.objects.get(pk=impersonator_id)
    target = request.auth
    end_impersonation(request, impersonator=impersonator)
    AuditLog.objects.create(
        actor=target,
        impersonator=impersonator,
        action="impersonation.end",
        target_type="User",
        target_id=str(target.pk),
    )
    return Status(204, None)
