"""Preset role seeding (PRD §4 "Tenancy and permissions"; phase-3.md A.4).

Owner/Admin/Member are global singleton ``Role`` rows — ``Role.organization
= None`` marks a system preset per that model's docstring — shared by
every organisation's memberships rather than duplicated three-per-org.
``seed_preset_roles()`` is idempotent (get-or-create, refreshed to the
current registry on every call) so the atomic organisation-creation
service in ``p3-orgs-api`` can call it unconditionally inside its
transaction without caring whether it is the first organisation ever
created.

Custom roles are a per-project feature flag (``settings
.KEEL_CUSTOM_ROLES_ENABLED``), off by default — the ``Role`` model and
``Perm.ROLES_MANAGE`` exist regardless, so enabling it is a settings
change, not a migration.
"""

from django.conf import settings

from keel.core.authz import registry
from keel.organizations.models import Role
from keel.organizations.permissions import Perm

PRESET_OWNER = "Owner"
PRESET_ADMIN = "Admin"
PRESET_MEMBER = "Member"

_ADMIN_EXCLUDED = {Perm.ORG_DELETE, Perm.ORG_TRANSFER}

# "Member holds the view codes plus resource CRUD" (PRD §4) — the view
# codes across every domain plus the demo resource's CRUD codes. A
# project's /new-resource adds its own resource's codes here.
_MEMBER_CODES = {
    Perm.ORG_VIEW,
    Perm.MEMBERS_VIEW,
    Perm.BILLING_VIEW,
    Perm.AUDIT_VIEW,
    Perm.WIDGETS_VIEW,
    Perm.WIDGETS_MANAGE,
    Perm.FILES_VIEW,
    Perm.FILES_MANAGE,
    Perm.JOBS_VIEW,
    Perm.JOBS_CREATE,
}


def _all_registered_codes() -> list[str]:
    return [code for code, _guard in registry]


def _preset_permissions() -> dict[str, list[str]]:
    all_codes = _all_registered_codes()
    return {
        PRESET_OWNER: sorted(all_codes),
        PRESET_ADMIN: sorted(code for code in all_codes if code not in _ADMIN_EXCLUDED),
        PRESET_MEMBER: sorted(code for code in all_codes if code in _MEMBER_CODES),
    }


def seed_preset_roles() -> dict[str, Role]:
    """Idempotently ensure the three global preset ``Role`` rows exist and
    hold the current registry's codes, returning them keyed by name."""
    roles: dict[str, Role] = {}
    for name, permissions in _preset_permissions().items():
        role, _created = Role.objects.get_or_create(
            organization=None,
            name=name,
            is_preset=True,
            defaults={"permissions": permissions},
        )
        if role.permissions != permissions:
            role.permissions = permissions
            role.save(update_fields=["permissions"])
        roles[name] = role
    return roles


def custom_roles_enabled() -> bool:
    return bool(getattr(settings, "KEEL_CUSTOM_ROLES_ENABLED", False))
