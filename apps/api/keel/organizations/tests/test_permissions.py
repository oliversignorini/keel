"""``organizations/permissions.py`` — the single source of truth for
permission codes and guards (PRD §4 invariant 2; phase-3.md A.1, A.2).

Every code declares one ``@allow_case`` and at least one ``@deny_case``
here. The generic ``test_guard_allow`` / ``test_guard_deny`` runners below
call ``has_perm`` and assert on the ``Decision`` — ``test_guard_deny``
always asserts ``decision.reason``, so a deny case cannot skip that
assertion (PRD invariant 2: "deny tests assert the reason, not merely
that access was refused").
"""

import pytest

from keel.accounts.models import User
from keel.core.authz import has_perm as core_has_perm
from keel.organizations.models import Membership, Organization, Role
from keel.organizations.permissions import DenialReason, Perm, has_perm, registered_denial_reasons
from keel.organizations.tests.guard_cases import ALLOW_CASES, DENY_CASES, allow_case, deny_case

pytestmark = pytest.mark.django_db

_seq = iter(range(1_000_000))


def _user() -> User:
    n = next(_seq)
    return User.objects.create_user(email=f"user{n}@example.com", password="s3cret-pass")


def _org(creator: User) -> Organization:
    n = next(_seq)
    return Organization.objects.create(name=f"Org {n}", slug=f"org-{n}", created_by=creator)


def _role(codes: list[str]) -> Role:
    n = next(_seq)
    return Role.objects.create(name=f"Fixture role {n}", permissions=list(codes))


def _member(org: Organization, codes: list[str], status: str = Membership.STATUS_ACTIVE) -> User:
    """An active member of ``org`` whose role holds exactly ``codes``."""
    user = _user()
    Membership.objects.create(organization=org, user=user, role=_role(codes), status=status)
    return user


def _simple(code: str) -> None:
    """Register the boilerplate allow/deny case for a role-only guard."""

    @allow_case(code)
    def _allow() -> tuple:
        creator = _user()
        org = _org(creator)
        actor = _member(org, [code])
        return actor, org, None

    @deny_case(code, "insufficient_role")
    def _deny() -> tuple:
        creator = _user()
        org = _org(creator)
        actor = _member(org, [])  # role holds no codes
        return actor, org, None


# --- Every simple, role-only code -----------------------------------------

for _code in (
    Perm.ORG_VIEW,
    Perm.ORG_UPDATE,
    Perm.ORG_DELETE,
    Perm.ORG_TRANSFER,
    Perm.MEMBERS_VIEW,
    Perm.MEMBERS_INVITE,
    Perm.MEMBERS_CHANGE_ROLE,
    Perm.ROLES_MANAGE,
    Perm.BILLING_VIEW,
    Perm.BILLING_MANAGE,
    Perm.AUDIT_VIEW,
    Perm.WIDGETS_VIEW,
    Perm.WIDGETS_MANAGE,
    Perm.FILES_VIEW,
    Perm.FILES_MANAGE,
    Perm.JOBS_VIEW,
    Perm.JOBS_CREATE,
):
    _simple(_code)


# --- Perm.MEMBERS_REMOVE — the subject-inspecting guard (A.2) -------------
# Denies removing the org's last owner, identified by permission code
# (Perm.ORG_TRANSFER), never by role name (PRD §4 invariant 2: "a role
# name must never appear in a conditional").


@allow_case(Perm.MEMBERS_REMOVE, label="removes_a_non_owner")
def _members_remove_allow() -> tuple:
    creator = _user()
    org = _org(creator)
    actor = _member(org, [Perm.MEMBERS_REMOVE])
    target = _member(org, [])  # an ordinary member, not an owner
    target_membership = Membership.objects.get(organization=org, user=target)
    return actor, org, target_membership


@deny_case(Perm.MEMBERS_REMOVE, "insufficient_role", label="lacks_the_code")
def _members_remove_deny_insufficient_role() -> tuple:
    creator = _user()
    org = _org(creator)
    actor = _member(org, [])
    target = _member(org, [])
    target_membership = Membership.objects.get(organization=org, user=target)
    return actor, org, target_membership


@deny_case(Perm.MEMBERS_REMOVE, "cannot_remove_last_owner", label="last_owner")
def _members_remove_deny_last_owner() -> tuple:
    creator = _user()
    org = _org(creator)
    owner_codes = [Perm.MEMBERS_REMOVE, Perm.ORG_TRANSFER]
    owner = _member(org, owner_codes)
    owner_membership = Membership.objects.get(organization=org, user=owner)
    # owner acts on themselves — the only owner in this organisation
    return owner, org, owner_membership


# --- Generic runners --------------------------------------------------


@pytest.mark.parametrize("case", ALLOW_CASES, ids=lambda c: f"{c.code}:{c.label}")
def test_guard_allow(case) -> None:
    user, organization, subject = case.build()

    decision = has_perm(user, organization, case.code, subject=subject)

    assert decision.allowed is True, decision


@pytest.mark.parametrize("case", DENY_CASES, ids=lambda c: f"{c.code}:{c.label}")
def test_guard_deny(case) -> None:
    user, organization, subject = case.build()

    decision = has_perm(user, organization, case.code, subject=subject)

    assert decision.allowed is False
    assert decision.reason == case.reason, decision


# --- Extra coverage: subject-inspection actually changes the outcome ------


def test_members_remove_allows_when_another_owner_exists() -> None:
    creator = _user()
    org = _org(creator)
    owner_codes = [Perm.MEMBERS_REMOVE, Perm.ORG_TRANSFER]
    actor = _member(org, owner_codes)
    second_owner = _member(org, owner_codes)
    second_owner_membership = Membership.objects.get(organization=org, user=second_owner)

    decision = has_perm(actor, org, Perm.MEMBERS_REMOVE, subject=second_owner_membership)

    assert decision.allowed is True


def test_members_remove_denies_removing_the_sole_owner_even_by_another_owner() -> None:
    creator = _user()
    org = _org(creator)
    owner_codes = [Perm.MEMBERS_REMOVE, Perm.ORG_TRANSFER]
    actor = _member(org, owner_codes)
    sole_owner = _member(org, [*owner_codes, Perm.MEMBERS_INVITE])
    # Make `actor` the only *other* owner removed from the picture: demote
    # actor's own membership away from ORG_TRANSFER so `sole_owner` really
    # is the only owner left.
    actor_membership = Membership.objects.get(organization=org, user=actor)
    actor_membership.role.permissions = [Perm.MEMBERS_REMOVE]
    actor_membership.role.save(update_fields=["permissions"])
    sole_owner_membership = Membership.objects.get(organization=org, user=sole_owner)

    decision = has_perm(actor, org, Perm.MEMBERS_REMOVE, subject=sole_owner_membership)

    assert decision.allowed is False
    assert decision.reason == "cannot_remove_last_owner"
    assert decision.details == {"membership_id": str(sole_owner_membership.pk)}


# --- Wiring sanity ----------------------------------------------------


def test_has_perm_is_reexported_from_organizations_permissions() -> None:
    assert has_perm is core_has_perm


def test_registered_denial_reasons_lists_every_deny_case_code() -> None:
    """api-patterns finding 18: the published set can't drift from what the
    guards above actually raise, because it's derived from the same
    ``DenialReason`` constants they use."""
    assert registered_denial_reasons() == sorted(
        {DenialReason.INSUFFICIENT_ROLE, DenialReason.CANNOT_REMOVE_LAST_OWNER}
    )
    for case in DENY_CASES:
        assert case.reason in registered_denial_reasons()


def test_perm_codes_match_prd() -> None:
    assert Perm.ORG_VIEW == "org.view"
    assert Perm.ORG_UPDATE == "org.update"
    assert Perm.ORG_DELETE == "org.delete"
    assert Perm.ORG_TRANSFER == "org.transfer"
    assert Perm.MEMBERS_VIEW == "members.view"
    assert Perm.MEMBERS_INVITE == "members.invite"
    assert Perm.MEMBERS_REMOVE == "members.remove"
    assert Perm.MEMBERS_CHANGE_ROLE == "members.change_role"
    assert Perm.ROLES_MANAGE == "roles.manage"
    assert Perm.BILLING_VIEW == "billing.view"
    assert Perm.BILLING_MANAGE == "billing.manage"
    assert Perm.AUDIT_VIEW == "audit.view"


def test_unauthenticated_and_non_member_are_denied_insufficient_role() -> None:
    creator = _user()
    org = _org(creator)
    outsider = _user()

    decision = has_perm(outsider, org, Perm.ORG_VIEW)

    assert decision.allowed is False
    assert decision.reason == "insufficient_role"


def test_suspended_member_is_denied() -> None:
    creator = _user()
    org = _org(creator)
    suspended = _member(org, [Perm.ORG_VIEW], status=Membership.STATUS_SUSPENDED)

    decision = has_perm(suspended, org, Perm.ORG_VIEW)

    assert decision.allowed is False
    assert decision.reason == "insufficient_role"


def test_denies_when_organization_is_none() -> None:
    creator = _user()

    decision = has_perm(creator, None, Perm.ORG_VIEW)

    assert decision.allowed is False
    assert decision.reason == "insufficient_role"


def test_denies_when_user_is_not_authenticated() -> None:
    creator = _user()
    org = _org(creator)
    from types import SimpleNamespace

    anonymous = SimpleNamespace(is_authenticated=False)

    decision = has_perm(anonymous, org, Perm.ORG_VIEW)

    assert decision.allowed is False
    assert decision.reason == "insufficient_role"


def test_removing_a_suspended_last_owner_is_not_blocked_by_the_last_owner_rule() -> None:
    """A suspended membership can't act as an owner, so removing it isn't
    subject to the "cannot remove the last owner" guard — only ACTIVE
    owner memberships count toward "last"."""
    creator = _user()
    org = _org(creator)
    actor = _member(org, [Perm.MEMBERS_REMOVE])
    suspended_owner = _member(org, [Perm.ORG_TRANSFER], status=Membership.STATUS_SUSPENDED)
    suspended_owner_membership = Membership.objects.get(organization=org, user=suspended_owner)

    decision = has_perm(actor, org, Perm.MEMBERS_REMOVE, subject=suspended_owner_membership)

    assert decision.allowed is True
