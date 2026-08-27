"""Ninja counterpart to ``keel.core.authz`` (PRD §4 invariant 2 and
invariant 7). Read that module's docstring first — the vocabulary
(``Decision``, ``Guard``, the registry, ``has_perm``) is unchanged and
lives there regardless of which framework is on top of it; this module
only replaces the base class Ninja resources declare against.

Ninja has no viewsets, no ``permission_classes``, and no ``initial()``
hook, so ``GlobalViewSet`` / ``OrgScopedViewSet``'s job — refuse at import
time to exist without ``required_permissions`` and either
``organization_scoped = True`` + ``test_factory`` or a
``GLOBAL_JUSTIFICATION``, and record itself in a walkable registry — is
reproduced here with a declarative resource class instead of a viewset
base class. A resource wraps one Ninja ``Router`` and declares, alongside
it, ``detail_url_template``: the literal, fully-qualified URL template
(e.g. ``"/api/v1/orgs/{org_slug}/widgets/{pk}/"``) for its retrieve-shaped
operation. The tenant-isolation meta-test (``ninja_tenant_isolation.py``)
formats real values into that template and drives it with Django's test
client against the live URLconf — closer to the truth than introspecting
Ninja's ``path_operations`` would be, and it is what actually proves the
route is wired, not merely declared (PRD §4 invariant 7's "the exemption
list is where leaks hide" applies exactly as much to an unmounted router).
"""

from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.utils.module_loading import import_string
from ninja import Router

from keel.core.authz import _resolve_organization
from keel.core.exceptions import PermissionDeniedWithReason
from keel.core.ninja_auth import session_auth


class GlobalResource:
    """Base for a Ninja resource over a table that is legitimately
    global. See ``keel.core.authz.GlobalViewSet`` — the contract is
    identical, only the framework underneath changed."""

    __abstract__ = True
    organization_scoped = False
    GLOBAL_JUSTIFICATION: str | None = None
    required_permissions: tuple[str, ...] | list[str] | None = None
    router: Router

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("__abstract__", False):
            return
        if not getattr(cls, "required_permissions", None):
            raise ImproperlyConfigured(f"{cls.__name__} must declare required_permissions.")
        if not cls.organization_scoped and not getattr(cls, "GLOBAL_JUSTIFICATION", None):
            raise ImproperlyConfigured(
                f"{cls.__name__} must declare organization_scoped = True or a "
                "GLOBAL_JUSTIFICATION string explaining why this table has no "
                "tenant boundary."
            )
        _global_resource_registry.append(cls)


_global_resource_registry: list[type["GlobalResource"]] = []


def registered_global_resources() -> list[type["GlobalResource"]]:
    return list(_global_resource_registry)


_scoped_resource_registry: list[type["OrgScopedResource"]] = []


def registered_scoped_resources() -> list[type["OrgScopedResource"]]:
    return list(_scoped_resource_registry)


class OrgScopedResource(GlobalResource):
    """Base for a Ninja resource scoped to an organisation. See
    ``keel.core.authz.OrgScopedViewSet``; ``resolve_and_authorize`` below
    replaces its ``initial()`` hook as something a route function calls
    explicitly at the top of its body (Ninja has no request-lifecycle
    hook to hang it off), and ``detail_url_template`` (module docstring)
    replaces the router-walk the DRF meta-test used."""

    __abstract__ = True
    organization_scoped = True
    organization_url_kwarg = "org_slug"
    test_factory: str | None = None
    detail_url_template: str | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("__abstract__", False):
            return
        if not cls.organization_scoped:
            # Opted out the same way a GlobalViewSet subclass does — the
            # GLOBAL_JUSTIFICATION check already ran in
            # GlobalResource.__init_subclass__ above.
            return
        if not getattr(cls, "test_factory", None):
            raise ImproperlyConfigured(
                f"{cls.__name__} declares organization_scoped = True and must "
                "also declare test_factory, the dotted path to a factory the "
                "cross-tenant meta-test uses to build rows in two "
                "organisations (PRD §4 invariant 7)."
            )
        if not getattr(cls, "detail_url_template", None):
            raise ImproperlyConfigured(
                f"{cls.__name__} must declare detail_url_template, the literal "
                "URL template (e.g. '/api/v1/orgs/{org_slug}/widgets/{pk}/') "
                "for its retrieve operation, so the tenant-isolation "
                "meta-test can drive the real route (PRD §4 invariant 7)."
            )
        _scoped_resource_registry.append(cls)


def resolve_and_authorize(
    request: Any, org_slug: str, required_permissions: tuple[str, ...] | list[str]
) -> Any:
    """Ninja route functions call this first: resolves the organisation
    (404 on a non-member or nonexistent slug — never 403, see
    ``keel.core.authz``'s module docstring) and runs every required
    permission code through ``has_perm``, raising
    ``PermissionDeniedWithReason`` on the first denial."""
    from keel.core.authz import has_perm

    organization = _resolve_organization(request, org_slug)
    if organization is None:
        raise Http404
    for code in required_permissions:
        decision = has_perm(request.auth, organization, code)
        if not decision.allowed:
            raise PermissionDeniedWithReason(
                code=decision.reason or "permission_denied", details=decision.details
            )
    return organization


def keel_router(**kwargs: Any) -> Router:
    """A Ninja ``Router`` pre-wired with this project's deny-by-default
    auth and general rate limiting (PRD §4 task 1.12, §3 NFR "Security")
    — every ``KeelAPI`` operation goes through ``session_auth`` and
    ``throttle`` the same way every DRF view went through
    ``DEFAULT_AUTHENTICATION_CLASSES`` / ``DEFAULT_THROTTLE_CLASSES``."""
    return Router(auth=session_auth, **kwargs)


__all__ = [
    "GlobalResource",
    "OrgScopedResource",
    "import_string",
    "keel_router",
    "registered_global_resources",
    "registered_scoped_resources",
    "resolve_and_authorize",
]
