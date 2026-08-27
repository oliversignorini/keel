"""Import-time checks on ``OrgScopedResource`` / ``GlobalResource`` — the
Ninja counterpart to ``test_authz.py``'s checks on
``OrgScopedViewSet`` / ``GlobalViewSet`` (PRD §4 invariant 7). Same
contract, different framework underneath; see
``keel/core/ninja_authz.py``'s module docstring.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured
from ninja import Router

from keel.core.ninja_authz import (
    GlobalResource,
    OrgScopedResource,
    registered_scoped_resources,
)


def fake_factory(organization: object) -> object:
    return organization


# --- Import-time checks --------------------------------------------------


def test_resource_without_required_permissions_raises_at_import_time() -> None:
    with pytest.raises(ImproperlyConfigured):

        class BadResource(OrgScopedResource):
            router = Router()
            test_factory = "keel.core.tests.test_ninja_authz.fake_factory"
            detail_url_template = "/api/v1/orgs/{org_slug}/bad/{pk}/"


def test_resource_without_organization_scoped_or_global_justification_raises() -> None:
    with pytest.raises(ImproperlyConfigured):

        class BadGlobalResource(GlobalResource):
            router = Router()
            required_permissions = ("fixture.view",)
            organization_scoped = False


def test_org_scoped_resource_without_test_factory_raises() -> None:
    with pytest.raises(ImproperlyConfigured):

        class BadOrgResource(OrgScopedResource):
            router = Router()
            required_permissions = ("fixture.view",)
            detail_url_template = "/api/v1/orgs/{org_slug}/bad/{pk}/"


def test_org_scoped_resource_without_detail_url_template_raises() -> None:
    with pytest.raises(ImproperlyConfigured):

        class BadOrgResource(OrgScopedResource):
            router = Router()
            required_permissions = ("fixture.view",)
            test_factory = "keel.core.tests.test_ninja_authz.fake_factory"


def test_org_scoped_resource_with_everything_declared_does_not_raise() -> None:
    class GoodOrgResource(OrgScopedResource):
        router = Router()
        required_permissions = ("fixture.view",)
        test_factory = "keel.core.tests.test_ninja_authz.fake_factory"
        detail_url_template = "/api/v1/orgs/{org_slug}/good/{pk}/"

    assert GoodOrgResource.organization_scoped is True


def test_global_resource_with_justification_does_not_raise() -> None:
    class GoodGlobalResource(GlobalResource):
        router = Router()
        required_permissions = ("fixture.view",)
        organization_scoped = False
        GLOBAL_JUSTIFICATION = "Reference data, identical across tenants."

    assert GoodGlobalResource.GLOBAL_JUSTIFICATION


def test_abstract_org_scoped_intermediate_base_skips_the_checks() -> None:
    class AbstractIntermediateResource(OrgScopedResource):
        __abstract__ = True

    assert AbstractIntermediateResource.test_factory is None


# --- The scoped-resource registry (PRD §4 invariant 7) -------------------


def test_org_scoped_resource_subclass_is_recorded_in_the_registry() -> None:
    class RecordedResource(OrgScopedResource):
        router = Router()
        required_permissions = ("fixture.view",)
        test_factory = "keel.core.tests.test_ninja_authz.fake_factory"
        detail_url_template = "/api/v1/orgs/{org_slug}/recorded/{pk}/"

    assert RecordedResource in registered_scoped_resources()


def test_abstract_org_scoped_subclass_is_not_recorded() -> None:
    before = set(registered_scoped_resources())

    class AbstractNotRecordedResource(OrgScopedResource):
        __abstract__ = True

    after = set(registered_scoped_resources())

    assert after == before


def test_org_scoped_subclass_opting_out_of_scoping_is_not_recorded() -> None:
    before = set(registered_scoped_resources())

    class OptedOutResource(OrgScopedResource):
        router = Router()
        required_permissions = ("fixture.view",)
        organization_scoped = False
        GLOBAL_JUSTIFICATION = "Fixture — deliberately opts out."

    after = set(registered_scoped_resources())

    assert after == before
