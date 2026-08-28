"""The KEEL_ORGANIZATION_RESOLVER implementation (PRD §4, "The
membership-resolution seam").

Returning ``None`` must mean *both* "no such slug" and "you are not an
active member" — indistinguishably, per PRD invariant 7's tenant-isolation
requirement that cross-org access answers 404, never 403.
"""

from types import SimpleNamespace

import pytest

from keel.accounts.models import User
from keel.organizations.models import Membership, Organization, Role
from keel.organizations.resolvers import resolve_organization

pytestmark = pytest.mark.django_db


def _user(email: str) -> User:
    return User.objects.create_user(email=email, password="s3cret-pass")


def _role(name: str = "Member") -> Role:
    return Role.objects.create(name=name, permissions=[])


def _request_for(user: User) -> SimpleNamespace:
    return SimpleNamespace(user=user)


def test_resolves_organization_for_active_member() -> None:
    owner = _user("owner@example.com")
    org = Organization.objects.create(name="Acme", slug="acme", created_by=owner)
    Membership.objects.create(
        organization=org, user=owner, role=_role(), status=Membership.STATUS_ACTIVE
    )

    resolved = resolve_organization(_request_for(owner), "acme")

    assert resolved == org


def test_returns_none_for_nonexistent_slug() -> None:
    someone = _user("someone@example.com")

    resolved = resolve_organization(_request_for(someone), "does-not-exist")

    assert resolved is None


def test_returns_none_for_non_member() -> None:
    owner = _user("owner2@example.com")
    outsider = _user("outsider@example.com")
    org = Organization.objects.create(name="Acme 2", slug="acme-2", created_by=owner)
    Membership.objects.create(
        organization=org, user=owner, role=_role(), status=Membership.STATUS_ACTIVE
    )

    resolved = resolve_organization(_request_for(outsider), "acme-2")

    assert resolved is None


def test_returns_none_for_suspended_member() -> None:
    owner = _user("owner3@example.com")
    suspended = _user("suspended@example.com")
    org = Organization.objects.create(name="Acme 3", slug="acme-3", created_by=owner)
    Membership.objects.create(
        organization=org, user=owner, role=_role(), status=Membership.STATUS_ACTIVE
    )
    Membership.objects.create(
        organization=org, user=suspended, role=_role(), status=Membership.STATUS_SUSPENDED
    )

    resolved = resolve_organization(_request_for(suspended), "acme-3")

    assert resolved is None


def test_missing_slug_and_non_member_are_indistinguishable() -> None:
    outsider = _user("outsider2@example.com")
    owner = _user("owner4@example.com")
    Organization.objects.create(name="Acme 4", slug="acme-4", created_by=owner)

    missing_slug_result = resolve_organization(_request_for(outsider), "totally-missing")
    not_a_member_result = resolve_organization(_request_for(outsider), "acme-4")

    assert missing_slug_result is None
    assert not_a_member_result is None
    assert missing_slug_result == not_a_member_result


def test_returns_none_for_soft_deleted_organization() -> None:
    from django.utils import timezone

    owner = _user("owner5@example.com")
    org = Organization.objects.create(
        name="Acme 5", slug="acme-5", created_by=owner, deleted_at=timezone.now()
    )
    Membership.objects.create(
        organization=org, user=owner, role=_role(), status=Membership.STATUS_ACTIVE
    )

    resolved = resolve_organization(_request_for(owner), "acme-5")

    assert resolved is None


def test_returns_none_for_unauthenticated_request() -> None:
    resolved = resolve_organization(SimpleNamespace(user=None), "acme")

    assert resolved is None
