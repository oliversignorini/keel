"""``GET /orgs/<slug>/billing/credits/`` (PRD §7's credits
endpoint list; docs/plans/phase-4.md Worktree C's ``<CreditMeter>``).

Both flag states are covered, which is the point of A.5: with
``BILLING_CREDITS`` off there is *no endpoint*, not an endpoint returning
zero — the web meter renders nothing at all in that state.
"""

import pytest
from django.test import Client as APIClient
from django.test import override_settings

from keel.accounts.models import User
from keel.billing import credits
from keel.billing.models import CreditBalance
from keel.organizations import services
from keel.organizations.models import Membership, Organization
from keel.organizations.roles import PRESET_MEMBER, seed_preset_roles

pytestmark = pytest.mark.django_db

_counter = 0


def _user(prefix: str = "user") -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(
        email=f"{prefix}-{_counter}@example.com", password="s3cret-pass"
    )


def _org_with_owner() -> tuple[Organization, User]:
    global _counter
    _counter += 1
    owner = _user("owner")
    org = services.create_organization(name="Acme", slug=f"acme-{_counter}", created_by=owner)
    return org, owner


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _url(org: Organization) -> str:
    return f"/api/v1/orgs/{org.slug}/billing/credits/"


@override_settings(BILLING_CREDITS=True)
def test_returns_the_balance_when_credits_are_enabled() -> None:
    org, owner = _org_with_owner()
    credits.grant(org, 250, reason="test top-up")

    response = _client_for(owner).get(_url(org))

    assert response.status_code == 200, response.json()
    assert response.json() == {"balance": 250}


@override_settings(BILLING_CREDITS=True)
def test_returns_zero_when_no_credit_balance_row_exists_yet() -> None:
    org, owner = _org_with_owner()
    assert not CreditBalance.objects.filter(organization=org).exists()

    response = _client_for(owner).get(_url(org))

    assert response.status_code == 200, response.json()
    assert response.json() == {"balance": 0}


@override_settings(BILLING_CREDITS=False)
def test_404s_when_credits_are_disabled() -> None:
    org, owner = _org_with_owner()

    response = _client_for(owner).get(_url(org))

    assert response.status_code == 404


@override_settings(BILLING_CREDITS=True)
def test_readable_by_billing_view_alone() -> None:
    org, _owner = _org_with_owner()
    member = _user("member")
    role = seed_preset_roles()[PRESET_MEMBER]
    Membership.objects.create(
        organization=org, user=member, role=role, status=Membership.STATUS_ACTIVE
    )

    response = _client_for(member).get(_url(org))

    assert response.status_code == 200, response.json()


@override_settings(BILLING_CREDITS=True)
def test_404s_for_a_nonmember() -> None:
    org, _owner = _org_with_owner()
    outsider = _user("outsider")

    response = _client_for(outsider).get(_url(org))

    assert response.status_code == 404
