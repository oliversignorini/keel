"""Authorization vocabulary made real (PRD §4 invariant 2, "Where is
authorization expressed?"; phase-3.md A.1, A.2).

``Decision``, the ``Guard`` protocol and the registry live in
``keel.core.authz`` — a base class built in Phase 1 that ``keel.core``
cannot import its own dependent from. This module is the file that
invariant means: the ``Perm`` codes and every guard implementation live
here, registered at import time, and ``has_perm`` is re-exported so call
sites read exactly as PRD §4 describes them.

**Only permission codes are ever checked in code. A role name must never
appear in a conditional.** The last-owner check in
``_members_remove_guard`` identifies the owner tier by the permission
code only the Owner preset holds (``Perm.ORG_TRANSFER``), never by
``role.name`` — see ``keel/organizations/roles.py`` for why that code is
the right one to key on.
"""

from typing import Any

from keel.core.authz import Decision, Guard, has_perm, registry
from keel.organizations.models import Membership

has_perm = has_perm  # re-exported so call sites read `permissions.has_perm`


class Perm:
    """Permission codes — the exact vocabulary PRD §4 "Tenancy and
    permissions" lists, plus one demo-resource group (``widgets.*``) for
    the ``Widget`` app ``/new-resource`` copies from."""

    ORG_VIEW = "org.view"
    ORG_UPDATE = "org.update"
    ORG_DELETE = "org.delete"
    ORG_TRANSFER = "org.transfer"
    MEMBERS_VIEW = "members.view"
    MEMBERS_INVITE = "members.invite"
    MEMBERS_REMOVE = "members.remove"
    MEMBERS_CHANGE_ROLE = "members.change_role"
    ROLES_MANAGE = "roles.manage"
    BILLING_VIEW = "billing.view"
    BILLING_MANAGE = "billing.manage"
    AUDIT_VIEW = "audit.view"
    WIDGETS_VIEW = "widgets.view"
    WIDGETS_MANAGE = "widgets.manage"
    FILES_VIEW = "files.view"
    FILES_MANAGE = "files.manage"
    JOBS_VIEW = "jobs.view"
    JOBS_CREATE = "jobs.create"


def _resolve_role_permissions(user: Any, organization: Any) -> frozenset[str]:
    if user is None or organization is None:
        return frozenset()
    if not getattr(user, "is_authenticated", True):
        return frozenset()
    membership = (
        Membership.objects.filter(
            organization=organization, user=user, status=Membership.STATUS_ACTIVE
        )
        .select_related("role")
        .first()
    )
    if membership is None:
        return frozenset()
    return frozenset(membership.role.permissions)


def _role_guard(code: str) -> Guard:
    """A guard whose implementation only looks at the role — the "simple"
    case PRD §4 invariant 2 describes ("a simple code is a guard whose
    implementation only looks at the role")."""

    def guard(user: Any, organization: Any, subject: Any | None = None) -> Decision:
        permissions = _resolve_role_permissions(user, organization)
        if code not in permissions:
            return Decision.deny("insufficient_role", details={"required": code})
        return Decision.allow()

    return guard


def is_last_active_owner(subject: Any) -> bool:
    """Whether ``subject`` (a ``Membership``) is the organisation's only
    active membership whose role holds ``Perm.ORG_TRANSFER`` — the
    permission code that identifies the Owner tier without naming it."""

    if subject.status != Membership.STATUS_ACTIVE:
        return False
    if Perm.ORG_TRANSFER not in subject.role.permissions:
        return False
    other_owner_exists = (
        Membership.objects.filter(
            organization_id=subject.organization_id,
            status=Membership.STATUS_ACTIVE,
            role__permissions__contains=[Perm.ORG_TRANSFER],
        )
        .exclude(pk=subject.pk)
        .exists()
    )
    return not other_owner_exists


def _members_remove_guard(user: Any, organization: Any, subject: Any | None = None) -> Decision:
    """The subject-inspecting guard (phase-3.md A.2): denies removing the
    organisation's last owner. Registered and declared exactly like any
    other guard — the distinction from ``_role_guard`` is implementation
    depth, not category (PRD §4 invariant 2)."""

    permissions = _resolve_role_permissions(user, organization)
    if Perm.MEMBERS_REMOVE not in permissions:
        return Decision.deny("insufficient_role", details={"required": Perm.MEMBERS_REMOVE})
    if subject is not None and is_last_active_owner(subject):
        return Decision.deny(
            "cannot_remove_last_owner",
            details={"membership_id": str(subject.pk)},
        )
    return Decision.allow()


registry.register(Perm.ORG_VIEW, _role_guard(Perm.ORG_VIEW))
registry.register(Perm.ORG_UPDATE, _role_guard(Perm.ORG_UPDATE))
registry.register(Perm.ORG_DELETE, _role_guard(Perm.ORG_DELETE))
registry.register(Perm.ORG_TRANSFER, _role_guard(Perm.ORG_TRANSFER))
registry.register(Perm.MEMBERS_VIEW, _role_guard(Perm.MEMBERS_VIEW))
registry.register(Perm.MEMBERS_INVITE, _role_guard(Perm.MEMBERS_INVITE))
registry.register(Perm.MEMBERS_REMOVE, _members_remove_guard)
registry.register(Perm.MEMBERS_CHANGE_ROLE, _role_guard(Perm.MEMBERS_CHANGE_ROLE))
registry.register(Perm.ROLES_MANAGE, _role_guard(Perm.ROLES_MANAGE))
registry.register(Perm.BILLING_VIEW, _role_guard(Perm.BILLING_VIEW))
registry.register(Perm.BILLING_MANAGE, _role_guard(Perm.BILLING_MANAGE))
registry.register(Perm.AUDIT_VIEW, _role_guard(Perm.AUDIT_VIEW))
registry.register(Perm.WIDGETS_VIEW, _role_guard(Perm.WIDGETS_VIEW))
registry.register(Perm.WIDGETS_MANAGE, _role_guard(Perm.WIDGETS_MANAGE))
registry.register(Perm.FILES_VIEW, _role_guard(Perm.FILES_VIEW))
registry.register(Perm.FILES_MANAGE, _role_guard(Perm.FILES_MANAGE))
registry.register(Perm.JOBS_VIEW, _role_guard(Perm.JOBS_VIEW))
registry.register(Perm.JOBS_CREATE, _role_guard(Perm.JOBS_CREATE))
