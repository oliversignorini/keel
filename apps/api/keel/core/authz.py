"""Authorization: the vocabulary and the Ninja binding layer over it
(PRD §4 invariant 2, "Where is authorization expressed?", and invariant
7). One module, not split by framework (posd#13) — Django Ninja is the
only framework in this tree, so a `ninja_` prefix named nothing.

**The vocabulary**: ``Decision``, the ``Guard`` protocol, the registry,
``has_perm``, and the membership-resolution seam. This part holds no
permission code, no role, and nothing that answers a question about a
user — that is ``organizations/permissions.py``, which imports this
module, registers real guards against real codes, and re-exports
``has_perm``. If you are about to write the string "org.view" in this
file, stop: it belongs in Phase 3.

**The membership-resolution seam.** ``OrgScopedResource`` must resolve
the organisation named in the URL and confirm the requesting user is a
member of it, but ``keel/core`` may not import ``keel.organizations``
(that import-linter contract is asserted in Phase 0 and must stay
green). So resolution is delegated to a settings-configured dotted path,
``settings.KEEL_ORGANIZATION_RESOLVER`` — a callable
``(request, org_slug: str) -> Organization | None`` that Phase 3 supplies
(likely backed by a ``Membership`` lookup). Returning ``None`` means "this
slug doesn't resolve, or it does and the requester isn't an active member
of it" — deliberately the same outcome for both, because PRD §4 invariant
7's tenant-isolation meta-test requires cross-org access to answer 404,
not 403 (a 403 would confirm the organisation exists to someone who isn't
in it).

**The Ninja binding layer**: ``GlobalResource``/``OrgScopedResource`` — the
base class a resource declares against — and ``resolve_and_authorize``,
the router constructors, and the shared error-response set every
operation attaches. Ninja has no viewsets, no ``permission_classes``, and
no ``initial()`` hook, so ``GlobalViewSet``/``OrgScopedViewSet``'s job —
refuse at import time to exist without ``required_permissions`` and
either ``organization_scoped = True`` + ``test_factory`` or a
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

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.utils.module_loading import import_string
from ninja import Router
from ninja.constants import NOT_SET

from keel.core.auth import optional_session_auth, session_auth
from keel.core.error_handlers import ErrorEnvelope
from keel.core.exceptions import PermissionDeniedWithReason


@dataclass(frozen=True)
class Decision:
    """The result of an authorization check. Not a bool — PRD §4 invariant 2
    explains why: a denial needs a machine-readable reason (it becomes the
    error envelope's ``code``) and structured details the caller can act on.
    """

    allowed: bool
    reason: str | None = None
    details: dict[str, Any] | None = None

    @classmethod
    def allow(cls) -> "Decision":
        return cls(allowed=True)

    @classmethod
    def deny(cls, reason: str, details: dict[str, Any] | None = None) -> "Decision":
        return cls(allowed=False, reason=reason, details=details)


class Guard(Protocol):
    def __call__(self, user: Any, organization: Any, subject: Any | None = None) -> Decision: ...


class UnregisteredPermissionCode(Exception):
    """Raised by ``has_perm`` on a code nobody registered.

    A typo in a permission code must fail loudly, not silently deny —
    silently denying makes the bug invisible to the developer who wrote it
    and visible only to the user who mysteriously can't do anything.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"No guard registered for permission code {code!r}.")


class PermissionRegistry:
    """A registry of permission codes to guards.

    Iteration order is insertion order and is part of the contract —
    Phase 3's meta-test (PRD §4 invariant 2: "every registered guard has a
    unit test with one allow case and one deny case") walks it, so it must
    stay a stable, inspectable surface rather than a dict comprehension
    buried in a closure.
    """

    def __init__(self) -> None:
        self._guards: dict[str, Guard] = {}

    def register(self, code: str, guard: Guard) -> Guard:
        self._guards[code] = guard
        return guard

    def get(self, code: str) -> Guard:
        try:
            return self._guards[code]
        except KeyError:
            raise UnregisteredPermissionCode(code) from None

    def __iter__(self) -> Iterator[tuple[str, Guard]]:
        return iter(self._guards.items())

    def __len__(self) -> int:
        return len(self._guards)


registry = PermissionRegistry()


def has_perm(user: Any, organization: Any, code: str, subject: Any | None = None) -> Decision:
    guard = registry.get(code)
    return guard(user, organization, subject=subject)


def _resolve_organization(request: Any, org_slug: str | None) -> Any:
    resolver_path = getattr(settings, "KEEL_ORGANIZATION_RESOLVER", None)
    if not resolver_path:
        raise ImproperlyConfigured(
            "settings.KEEL_ORGANIZATION_RESOLVER is not configured. keel.core "
            "cannot resolve organisation membership itself (it must not import "
            "keel.organizations); set it to a dotted path 'module.callable' "
            "with signature (request, org_slug: str) -> Organization | None. "
            "See keel/core/authz.py module docstring for the full contract."
        )
    resolver = import_string(resolver_path)
    return resolver(request, org_slug)


# --- Ninja binding layer ---------------------------------------------------


class GlobalResource:
    """Base for a Ninja resource over a table that is legitimately
    global. ``OrgScopedResource`` below is the tenant-scoped counterpart —
    same contract, plus the membership check."""

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
    """Base for a Ninja resource scoped to an organisation.
    ``resolve_and_authorize`` below is what a route function calls
    explicitly at the top of its body to enforce the scope (Ninja has no
    request-lifecycle hook to hang it off), and ``detail_url_template``
    (module docstring) is what lets the tenant-isolation meta-test drive
    the real, mounted route."""

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
    (404 on a non-member or nonexistent slug — never 403, see this
    module's docstring) and runs every required permission code through
    ``has_perm``, raising ``PermissionDeniedWithReason`` on the first
    denial."""
    organization = _resolve_organization(request, org_slug)
    if organization is None:
        raise Http404
    for code in required_permissions:
        decision = has_perm(request.auth, organization, code)
        if not decision.allowed:
            raise PermissionDeniedWithReason(
                code=decision.reason or "permission_denied", denial=decision.details
            )
    return organization


# {400, 401, 403, 404, 409, 422, 429}: the status set the codebase's own
# DomainError subclasses (keel.core.exceptions) actually raise across the
# six migrated apps. Attached to every operation built through _KeelRouter
# below (api-patterns finding 3) so the OpenAPI document — and the
# generated TypeScript client — describes the envelope the exception
# handlers (keel.core.error_handlers) actually produce, instead of
# leaving every error typed ``unknown``.
_DEFAULT_ERROR_RESPONSES: dict[int, Any] = {
    400: ErrorEnvelope,
    401: ErrorEnvelope,
    403: ErrorEnvelope,
    404: ErrorEnvelope,
    409: ErrorEnvelope,
    422: ErrorEnvelope,
    429: ErrorEnvelope,
}


def _with_default_errors(response: Any) -> dict[Any, Any]:
    if response is NOT_SET:
        # Ninja only special-cases NOT_SET (skip response validation
        # entirely) when `response` is passed bare, not as a dict value —
        # `Any` is the closest equivalent once every operation is forced
        # into dict form to attach the shared error responses below: it
        # still validates against (and passes through) an arbitrary body.
        merged: dict[Any, Any] = {200: Any}
    elif isinstance(response, dict):
        merged = dict(response)
    else:
        merged = {200: response}
    for status, schema in _DEFAULT_ERROR_RESPONSES.items():
        merged.setdefault(status, schema)
    return merged


class _KeelRouter(Router):
    """A ``ninja.Router`` whose every operation is declared with the
    project's default error-response set (see ``_DEFAULT_ERROR_RESPONSES``
    above) merged into whatever ``response=`` the route already declares —
    an operation's own explicit schema for one of those statuses (e.g. a
    custom 404 payload) is never overridden. Every route built through one
    of this module's router constructors gets this for free; nothing
    below repeats the error-response set per call site."""

    def api_operation(
        self,
        methods: list[str],
        path: str,
        *,
        response: Any = NOT_SET,
        **kwargs: Any,
    ) -> Any:
        return super().api_operation(
            methods, path, response=_with_default_errors(response), **kwargs
        )


def _router(*, auth: Any, **kwargs: Any) -> Router:
    """Single internal constructor every sanctioned router builder below
    funnels through, so a new one (or a change to how routers are built)
    can't silently miss one of the three named cases. Rate limiting is not
    wired here — it is a request-layer concern
    (``keel.core.throttle.ThrottleMiddleware``) applied uniformly ahead of
    routing, regardless of which of these a route is mounted with (PRD §3
    NFR "Security")."""
    return _KeelRouter(auth=auth, **kwargs)


def keel_router(**kwargs: Any) -> Router:
    """A Ninja ``Router`` pre-wired with this project's deny-by-default
    auth (PRD §4 task 1.12) — every operation goes through
    ``session_auth``."""
    return _router(auth=session_auth, **kwargs)


def public_router(**kwargs: Any) -> Router:
    """Explicitly public: no session required (e.g. ``GET /plans/``, the
    Stripe webhook, which authenticates its own signature). Use this
    instead of a bare ``Router(auth=None)`` so ``test_ninja_wiring.py``'s
    deny-by-default walk can recognise the router as *declared* public
    rather than merely defaulted-open."""
    return _router(auth=None, **kwargs)


def optional_auth_router(**kwargs: Any) -> Router:
    """Works signed in or signed out — every operation goes through
    ``optional_session_auth`` (PRD §6 "Invitation"). ``request.auth`` may
    be an ``AnonymousUser``; an authenticated write still gets the CSRF
    check."""
    return _router(auth=optional_session_auth, **kwargs)


__all__ = [
    "Decision",
    "GlobalResource",
    "Guard",
    "OrgScopedResource",
    "PermissionRegistry",
    "UnregisteredPermissionCode",
    "has_perm",
    "keel_router",
    "optional_auth_router",
    "public_router",
    "registered_global_resources",
    "registered_scoped_resources",
    "registry",
    "resolve_and_authorize",
]
