"""Preset role seeding (PRD §4 "Tenancy and permissions").

``seed_preset_roles()`` is the function the organisation-creation service
calls inside its atomic transaction — this module owns and tests the
function itself, not the transaction that calls it.
"""

import pytest

from keel.core.authz import registry
from keel.organizations.models import Role
from keel.organizations.permissions import Perm
from keel.organizations.roles import (
    PRESET_ADMIN,
    PRESET_MEMBER,
    PRESET_OWNER,
    custom_roles_enabled,
    seed_preset_roles,
)

pytestmark = pytest.mark.django_db


def _all_registered_codes() -> set[str]:
    return {code for code, _guard in registry}


def test_seed_creates_three_preset_roles() -> None:
    roles = seed_preset_roles()

    assert set(roles) == {PRESET_OWNER, PRESET_ADMIN, PRESET_MEMBER}
    assert Role.objects.filter(is_preset=True, organization=None).count() == 3


def test_seed_is_idempotent() -> None:
    seed_preset_roles()
    seed_preset_roles()

    assert Role.objects.filter(is_preset=True, organization=None).count() == 3


def test_owner_holds_every_registered_code() -> None:
    roles = seed_preset_roles()

    assert set(roles[PRESET_OWNER].permissions) == _all_registered_codes()


def test_admin_holds_everything_except_delete_and_transfer() -> None:
    roles = seed_preset_roles()

    admin_permissions = set(roles[PRESET_ADMIN].permissions)

    assert Perm.ORG_DELETE not in admin_permissions
    assert Perm.ORG_TRANSFER not in admin_permissions
    assert admin_permissions == _all_registered_codes() - {Perm.ORG_DELETE, Perm.ORG_TRANSFER}


def test_member_holds_view_codes_plus_resource_crud() -> None:
    roles = seed_preset_roles()

    member_permissions = set(roles[PRESET_MEMBER].permissions)

    assert Perm.ORG_VIEW in member_permissions
    assert Perm.MEMBERS_VIEW in member_permissions
    assert Perm.WIDGETS_VIEW in member_permissions
    assert Perm.WIDGETS_MANAGE in member_permissions
    assert Perm.ORG_DELETE not in member_permissions
    assert Perm.MEMBERS_REMOVE not in member_permissions
    assert Perm.ROLES_MANAGE not in member_permissions


def test_seed_refreshes_a_stale_preset_role_to_the_current_registry() -> None:
    Role.objects.create(
        organization=None, name=PRESET_OWNER, is_preset=True, permissions=["stale.code"]
    )

    roles = seed_preset_roles()

    assert roles[PRESET_OWNER].permissions == sorted(_all_registered_codes())
    assert Role.objects.filter(is_preset=True, organization=None, name=PRESET_OWNER).count() == 1


def test_custom_roles_disabled_by_default(settings) -> None:
    assert settings.KEEL_CUSTOM_ROLES_ENABLED is False
    assert custom_roles_enabled() is False


def test_custom_roles_enabled_reflects_setting(settings) -> None:
    settings.KEEL_CUSTOM_ROLES_ENABLED = True

    assert custom_roles_enabled() is True
