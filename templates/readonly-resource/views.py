"""Views, read-only edition (PRD §7; CLAUDE.md's per-app file shape).
List and retrieve only — no POST, no PATCH, no DELETE, and so no write
permission codes and no mutating services to audit.

The tenant boundary is enforced exactly as it is on a writable resource:
``organization_scoped = True`` plus ``test_factory`` and
``detail_url_template``, so the cross-org meta-test walks this resource
too. Read-only is not a reason to be outside invariant 6.
"""

from typing import Any

from keel.__app__ import selectors
from keel.__app__.models import __Resource__
from keel.__app__.schemas import __Resource__Out
from keel.core.authz import OrgScopedResource, keel_router, resolve_and_authorize
from keel.core.pagination import Page, paginate
from keel.core.selectors import get_scoped_or_404
from keel.organizations.permissions import Perm

# keel:if crud_permissions
_VIEW = Perm.__RESOURCE___VIEW
# keel:endif
# keel:if manage_permissions
_VIEW = Perm.__RESOURCES___VIEW
# keel:endif


class __Resource__Resource(OrgScopedResource):
    """``/orgs/<org_slug>/__resources__/`` — the org-scoped read-only
    endpoint for ``__Resource__``."""

    router = keel_router(tags=["__resources__"])
    organization_scoped = True
    test_factory = "keel.__app__.tests.factories.__resource___factory"
    required_permissions = (_VIEW,)
    detail_url_template = "/api/v1/orgs/{org_slug}/__resources__/{id}/"


router = __Resource__Resource.router


@router.get(
    "/{org_slug}/__resources__/", response=Page[__Resource__Out], operation_id="list__Resources__"
)
def list___resources__(
    request: Any, org_slug: str, cursor: str | None = None, limit: int | None = None
) -> dict:
    organization = resolve_and_authorize(request, org_slug, (_VIEW,))
    queryset = selectors.list___resources__(organization)
    return paginate(request, queryset)


@router.get(
    "/{org_slug}/__resources__/{id}/",
    response=__Resource__Out,
    operation_id="retrieve__Resource__",
)
def retrieve___resource__(request: Any, org_slug: str, id: str) -> __Resource__:
    organization = resolve_and_authorize(request, org_slug, (_VIEW,))
    return get_scoped_or_404(selectors.list___resources__(organization), id)
