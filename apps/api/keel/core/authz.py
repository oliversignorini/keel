"""Authorization vocabulary (PRD §4 invariant 2, "Where is authorization
expressed?", and the v1.2 note "Where the type lives, and why it is not in
this file").

This module holds the *vocabulary* only: ``Decision``, the ``Guard``
protocol, the registry, ``has_perm``, and the membership-resolution seam.
It contains no permission code, no role, and nothing that answers a
question about a user — that is ``organizations/permissions.py``, which
imports this module, registers real guards against real codes, and
re-exports ``has_perm``. If you are about to write the string "org.view"
in this file, stop: it belongs in Phase 3.

The base class a resource declares against lives in
``keel/core/ninja_authz.py`` (``GlobalResource`` / ``OrgScopedResource``)
— it is framework-facing, this file is not.

**The membership-resolution seam.** ``OrgScopedResource`` must resolve the
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
from django.utils.module_loading import import_string


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
