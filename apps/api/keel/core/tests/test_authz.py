"""The authorization *vocabulary* (PRD §4 invariant 2): ``Decision``, the
registry, ``has_perm``, and the membership-resolution seam.

The base class a resource declares against, and its import-time checks,
moved to ``keel/core/ninja_authz.py`` when DRF was removed — those are
tested in ``test_ninja_authz.py``. What is left here is framework-free and
is what every guard and every route ultimately runs through.
"""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from keel.core.authz import (
    Decision,
    PermissionRegistry,
    UnregisteredPermissionCode,
    _resolve_organization,
    has_perm,
)

# --- Decision --------------------------------------------------------------


def test_decision_allow_is_allowed_with_no_reason() -> None:
    decision = Decision.allow()

    assert decision.allowed is True
    assert decision.reason is None
    assert decision.details is None


def test_decision_deny_carries_reason_and_details() -> None:
    decision = Decision.deny("insufficient_role", details={"required": "org.update"})

    assert decision.allowed is False
    assert decision.reason == "insufficient_role"
    assert decision.details == {"required": "org.update"}


def test_decision_is_frozen() -> None:
    decision = Decision.allow()

    with pytest.raises(FrozenInstanceError):
        decision.allowed = False  # type: ignore[misc]


# --- PermissionRegistry ------------------------------------------------


def test_registry_register_and_get() -> None:
    registry = PermissionRegistry()

    def guard(user, organization, subject=None):
        return Decision.allow()

    registry.register("fixture.code", guard)

    assert registry.get("fixture.code") is guard


def test_registry_get_unregistered_code_raises() -> None:
    registry = PermissionRegistry()

    with pytest.raises(UnregisteredPermissionCode):
        registry.get("fixture.missing")


def test_registry_iteration_is_stable_and_inspectable() -> None:
    registry = PermissionRegistry()
    guard_a = lambda user, organization, subject=None: Decision.allow()  # noqa: E731
    guard_b = lambda user, organization, subject=None: Decision.allow()  # noqa: E731

    registry.register("a.code", guard_a)
    registry.register("b.code", guard_b)

    assert list(registry) == [("a.code", guard_a), ("b.code", guard_b)]
    assert len(registry) == 2


# --- has_perm ------------------------------------------------------------


def test_has_perm_resolves_through_registry() -> None:
    from keel.core import authz

    def guard(user, organization, subject=None):
        return Decision.allow()

    authz.registry.register("fixture.allow", guard)

    decision = has_perm(user=None, organization=None, code="fixture.allow")

    assert decision.allowed is True


def test_has_perm_passes_the_subject_through_to_the_guard() -> None:
    """State denials (PRD §4 invariant 2) depend on the guard inspecting
    the row, so the subject must reach it rather than being dropped."""
    from keel.core import authz

    seen: dict[str, Any] = {}

    def guard(user, organization, subject=None):
        seen["subject"] = subject
        return Decision.deny("cannot_remove_last_owner")

    authz.registry.register("fixture.subject", guard)
    row = SimpleNamespace(pk=1)

    decision = has_perm(user=None, organization=None, code="fixture.subject", subject=row)

    assert seen["subject"] is row
    assert decision.reason == "cannot_remove_last_owner"


def test_has_perm_on_unregistered_code_raises_rather_than_denying() -> None:
    with pytest.raises(UnregisteredPermissionCode):
        has_perm(user=None, organization=None, code="fixture.definitely_not_registered")


# --- The membership-resolution seam --------------------------------------


def fixture_org_resolver(request, org_slug):
    if org_slug == "missing":
        return None
    return SimpleNamespace(pk=org_slug, slug=org_slug)


def test_resolve_organization_delegates_to_the_configured_dotted_path(settings: Any) -> None:
    settings.KEEL_ORGANIZATION_RESOLVER = f"{__name__}.fixture_org_resolver"

    organization = _resolve_organization(request=None, org_slug="acme")

    assert organization.slug == "acme"


def test_resolve_organization_returns_none_for_a_slug_the_resolver_rejects(
    settings: Any,
) -> None:
    """One outcome for "no such org" and "not a member" alike — a 403
    would confirm the organisation exists to someone outside it (PRD §4
    invariant 7); callers turn this ``None`` into a 404."""
    settings.KEEL_ORGANIZATION_RESOLVER = f"{__name__}.fixture_org_resolver"

    assert _resolve_organization(request=None, org_slug="missing") is None


def test_organization_resolver_unconfigured_raises_improperly_configured(
    settings: Any,
) -> None:
    settings.KEEL_ORGANIZATION_RESOLVER = None

    with pytest.raises(ImproperlyConfigured):
        _resolve_organization(request=None, org_slug="acme")
