from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from keel.core.authz import (
    Decision,
    GlobalViewSet,
    HasOrgPermission,
    OrgScopedViewSet,
    PermissionRegistry,
    UnregisteredPermissionCode,
    has_perm,
)
from keel.core.exceptions import PermissionDeniedWithReason

pytestmark = pytest.mark.django_db


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


def test_has_perm_resolves_through_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    from keel.core import authz

    def guard(user, organization, subject=None):
        return Decision.allow()

    authz.registry.register("fixture.allow", guard)

    decision = has_perm(user=None, organization=None, code="fixture.allow")

    assert decision.allowed is True


def test_has_perm_on_unregistered_code_raises_rather_than_denying() -> None:
    with pytest.raises(UnregisteredPermissionCode):
        has_perm(user=None, organization=None, code="fixture.definitely_not_registered")


# --- HasOrgPermission ------------------------------------------------------


def test_has_org_permission_allows_when_decision_allows() -> None:
    from keel.core import authz

    authz.registry.register(
        "fixture.allow_perm", lambda user, organization, subject=None: Decision.allow()
    )

    view = SimpleNamespace(required_permissions=["fixture.allow_perm"], organization=object())
    request = SimpleNamespace(user=object())

    assert HasOrgPermission().has_permission(request, view) is True


def test_has_org_permission_raises_permission_denied_with_reason_on_deny() -> None:
    from keel.core import authz

    authz.registry.register(
        "fixture.deny_perm",
        lambda user, organization, subject=None: Decision.deny(
            "insufficient_role", details={"required": "org.update"}
        ),
    )

    view = SimpleNamespace(required_permissions=["fixture.deny_perm"], organization=object())
    request = SimpleNamespace(user=object())

    with pytest.raises(PermissionDeniedWithReason) as exc_info:
        HasOrgPermission().has_permission(request, view)

    assert exc_info.value.code == "insufficient_role"
    assert exc_info.value.details == {"required": "org.update"}


# --- Import-time checks on OrgScopedViewSet / GlobalViewSet ------------


def test_viewset_without_required_permissions_raises_at_import_time() -> None:
    with pytest.raises(ImproperlyConfigured):

        class BadViewSet(OrgScopedViewSet):
            test_factory = "keel.core.tests.test_authz.fake_factory"


def test_viewset_without_organization_scoped_or_global_justification_raises() -> None:
    with pytest.raises(ImproperlyConfigured):

        class BadGlobalViewSet(GlobalViewSet):
            required_permissions = ("fixture.view",)
            organization_scoped = False


def test_org_scoped_viewset_without_test_factory_raises() -> None:
    with pytest.raises(ImproperlyConfigured):

        class BadOrgViewSet(OrgScopedViewSet):
            required_permissions = ("fixture.view",)


def test_org_scoped_viewset_with_everything_declared_does_not_raise() -> None:
    class GoodOrgViewSet(OrgScopedViewSet):
        required_permissions = ("fixture.view",)
        test_factory = "keel.core.tests.test_authz.fake_factory"

    assert GoodOrgViewSet.organization_scoped is True


def test_global_viewset_with_justification_does_not_raise() -> None:
    class GoodGlobalViewSet(GlobalViewSet):
        required_permissions = ("fixture.view",)
        organization_scoped = False
        GLOBAL_JUSTIFICATION = "Reference data, identical across tenants."

    assert GoodGlobalViewSet.GLOBAL_JUSTIFICATION


# --- End-to-end: Decision.deny reaches the client as a 403 envelope -------


def fixture_org_resolver(request, org_slug):
    if org_slug == "missing":
        return None
    return SimpleNamespace(pk=org_slug, slug=org_slug)


def test_decision_deny_reaches_client_as_403_envelope(settings: Any) -> None:
    from keel.core import authz

    authz.registry.register(
        "fixture.e2e_deny",
        lambda user, organization, subject=None: Decision.deny(
            "insufficient_role", details={"required": "org.update"}
        ),
    )

    class FixtureDenyViewSet(OrgScopedViewSet):
        required_permissions = ("fixture.e2e_deny",)
        test_factory = "keel.core.tests.test_authz.fake_factory"

        def list(self, request, *args, **kwargs):
            return Response({"ok": True})

    settings.KEEL_ORGANIZATION_RESOLVER = f"{__name__}.fixture_org_resolver"
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "EXCEPTION_HANDLER": "keel.core.exceptions.exception_handler",
    }

    request = APIRequestFactory().get("/fake/acme/things/")
    request.user = SimpleNamespace(is_authenticated=True, is_active=True)
    view = FixtureDenyViewSet.as_view({"get": "list"})

    response = view(request, org_slug="acme")
    response.render()

    assert response.status_code == 403
    assert response.data["error"]["code"] == "insufficient_role"
    assert response.data["error"]["details"] == {"required": "org.update"}


def test_org_scoped_viewset_404s_when_organization_does_not_resolve(
    settings: Any,
) -> None:
    from keel.core import authz

    authz.registry.register(
        "fixture.e2e_missing_org",
        lambda user, organization, subject=None: Decision.allow(),
    )

    class FixtureMissingOrgViewSet(OrgScopedViewSet):
        required_permissions = ("fixture.e2e_missing_org",)
        test_factory = "keel.core.tests.test_authz.fake_factory"

        def list(self, request, *args, **kwargs):
            return Response({"ok": True})

    settings.KEEL_ORGANIZATION_RESOLVER = f"{__name__}.fixture_org_resolver"

    request = APIRequestFactory().get("/fake/missing/things/")
    request.user = SimpleNamespace(is_authenticated=True, is_active=True)
    view = FixtureMissingOrgViewSet.as_view({"get": "list"})

    response = view(request, org_slug="missing")
    response.render()

    assert response.status_code == 404


def test_organization_resolver_unconfigured_raises_improperly_configured(
    settings: Any,
) -> None:
    from keel.core import authz

    authz.registry.register(
        "fixture.e2e_unconfigured",
        lambda user, organization, subject=None: Decision.allow(),
    )

    class FixtureUnconfiguredViewSet(OrgScopedViewSet):
        required_permissions = ("fixture.e2e_unconfigured",)
        test_factory = "keel.core.tests.test_authz.fake_factory"

        def list(self, request, *args, **kwargs):
            return Response({"ok": True})

    settings.KEEL_ORGANIZATION_RESOLVER = None

    request = APIRequestFactory().get("/fake/acme/things/")
    request.user = SimpleNamespace(is_authenticated=True, is_active=True)
    view = FixtureUnconfiguredViewSet.as_view({"get": "list"})

    with pytest.raises(ImproperlyConfigured):
        view(request, org_slug="acme")
