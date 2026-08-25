"""Authorization vocabulary (PRD §4 invariant 2, "Where is authorization
expressed?", and the v1.2 note "Where the type lives, and why it is not in
this file").

This module holds the *vocabulary* only: ``Decision``, the ``Guard``
protocol, the registry, ``has_perm``, ``HasOrgPermission``, and the base
viewsets. It contains no permission code, no role, and nothing that
answers a question about a user — that is ``organizations/permissions.py``,
which imports this module, registers real guards against real codes, and
re-exports ``has_perm``. If you are about to write the string "org.view"
in this file, stop: it belongs in Phase 3.

**The membership-resolution seam.** ``OrgScopedViewSet`` must resolve the
organisation named in the URL and confirm the requesting user is a member
of it, but ``keel/core`` may not import ``keel.organizations`` (that
import-linter contract is asserted in Phase 0 and must stay green). So
resolution is delegated to a settings-configured dotted path,
``settings.KEEL_ORGANIZATION_RESOLVER`` — a callable
``(request, org_slug: str) -> Organization | None`` that Phase 3 supplies
(likely backed by a ``Membership`` lookup). Returning ``None`` means "this
slug doesn't resolve, or it does and the requester isn't an active member
of it" — deliberately the same outcome for both, because PRD §4 invariant
7's tenant-isolation meta-test requires cross-org access to answer 404,
not 403 (a 403 would confirm the organisation exists to someone who isn't
in it). Phase 3's job is exactly one function at that dotted path; nothing
else in this file needs to change.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.utils.module_loading import import_string
from rest_framework import viewsets
from rest_framework.permissions import BasePermission

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


class HasOrgPermission(BasePermission):
    """Reads ``required_permissions`` off the view, resolves each through
    ``has_perm``, and raises ``PermissionDeniedWithReason`` — whose
    envelope ``code`` is ``Decision.reason`` and ``details`` is
    ``Decision.details`` — on the first denial.
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        codes = getattr(view, "required_permissions", None) or []
        organization = getattr(view, "organization", None)
        for code in codes:
            decision = has_perm(request.user, organization, code)
            if not decision.allowed:
                raise PermissionDeniedWithReason(
                    code=decision.reason or "permission_denied",
                    details=decision.details,
                )
        return True


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


class GlobalViewSet(viewsets.GenericViewSet):
    """Base for viewsets over tables that are legitimately global.

    Every subclass must declare ``required_permissions`` and must declare
    either ``organization_scoped = True`` (use ``OrgScopedViewSet`` instead)
    or a ``GLOBAL_JUSTIFICATION`` string explaining why the table has no
    tenant boundary. Both are enforced at import time via
    ``__init_subclass__`` — PRD §4 invariant 7's tenant-scoping rule must
    fail the build, not a request.
    """

    __abstract__ = True
    organization_scoped = False
    GLOBAL_JUSTIFICATION: str | None = None
    required_permissions: tuple[str, ...] | list[str] | None = None

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


class OrgScopedViewSet(GlobalViewSet):
    """Resolves the organisation from the URL, checks membership, and
    filters the queryset — all before any view code runs (PRD §4,
    "Tenancy and permissions"). See the module docstring for the
    membership-resolution seam.
    """

    __abstract__ = True
    organization_scoped = True
    permission_classes = (HasOrgPermission,)
    organization_url_kwarg = "org_slug"
    test_factory: str | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("__abstract__", False):
            return
        if cls.organization_scoped and not getattr(cls, "test_factory", None):
            raise ImproperlyConfigured(
                f"{cls.__name__} declares organization_scoped = True and must "
                "also declare test_factory, the dotted path to a factory the "
                "cross-tenant meta-test uses to build rows in two "
                "organisations (PRD §4 invariant 7)."
            )

    def initial(self, request: Any, *args: Any, **kwargs: Any) -> None:
        organization = _resolve_organization(request, kwargs.get(self.organization_url_kwarg))
        if organization is None:
            raise Http404
        self.organization = organization
        super().initial(request, *args, **kwargs)

    def get_queryset(self) -> Any:
        return super().get_queryset().for_organization(self.organization)
