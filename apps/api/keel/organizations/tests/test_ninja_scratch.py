"""Stage 10.A's stage gate (docs/plans/phase-10.md): exercises every core
Ninja primitive — auth (401 vs 403), the error envelope, org scoping
(404, never 403), cursor pagination, and throttling — against
``keel.organizations.tests.ninja_scratch_fixture``'s fixture resource
before any real app moves off DRF. Deleted alongside that fixture module
in 10.B.
"""

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from keel.accounts.models import User
from keel.organizations.models import Membership, Organization, Role
from keel.organizations.permissions import Perm

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.urls("keel.organizations.tests.urls_ninja_scratch"),
]


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def org_and_member():
    role = Role.objects.create(name="Scratch role", permissions=[Perm.MEMBERS_VIEW])
    creator = User.objects.create_user(email="scratch-owner@example.com", password="s3cret-pass")
    org = Organization.objects.create(name="Scratch Org", slug="scratch-org", created_by=creator)
    user = User.objects.create_user(email="scratch-member@example.com", password="s3cret-pass")
    membership = Membership.objects.create(
        organization=org, user=user, role=role, status=Membership.STATUS_ACTIVE
    )
    return org, user, membership


def test_anonymous_request_gets_401_not_authenticated(org_and_member):
    org, _user, _membership = org_and_member
    client = Client()

    response = client.get(f"/api/v1/__scratch__/{org.slug}/scratch/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_authenticated_unpermitted_gets_403_with_decision_reason(org_and_member):
    org, user, _membership = org_and_member
    client = Client()
    client.force_login(user)

    response = client.get(f"/api/v1/__scratch__/{org.slug}/scratch/admin-only/")

    assert response.status_code == 403
    body = response.json()
    assert "code" in body["error"]
    assert body["error"]["code"] != "not_authenticated"


def test_cross_org_row_answers_404_never_403(org_and_member):
    _org, user, membership = org_and_member
    other_creator = User.objects.create_user(
        email="other-owner@example.com", password="s3cret-pass"
    )
    other_org = Organization.objects.create(
        name="Other Org", slug="other-org", created_by=other_creator
    )
    other_role = Role.objects.create(name="Other role", permissions=[Perm.MEMBERS_VIEW])
    Membership.objects.create(
        organization=other_org, user=user, role=other_role, status=Membership.STATUS_ACTIVE
    )
    client = Client()
    client.force_login(user)

    response = client.get(f"/api/v1/__scratch__/{other_org.slug}/scratch/{membership.pk}/")

    assert response.status_code == 404


def test_nonmember_gets_404_for_the_organization_itself(org_and_member):
    org, _user, _membership = org_and_member
    outsider = User.objects.create_user(email="outsider@example.com", password="s3cret-pass")
    client = Client()
    client.force_login(outsider)

    response = client.get(f"/api/v1/__scratch__/{org.slug}/scratch/")

    assert response.status_code == 404


def test_list_is_cursor_paginated(org_and_member):
    org, user, _membership = org_and_member
    for i in range(3):
        role = Role.objects.create(name=f"Extra role {i}", permissions=[Perm.MEMBERS_VIEW])
        extra_user = User.objects.create_user(
            email=f"extra-{i}@example.com", password="s3cret-pass"
        )
        Membership.objects.create(
            organization=org, user=extra_user, role=role, status=Membership.STATUS_ACTIVE
        )
    client = Client()
    client.force_login(user)

    response = client.get(f"/api/v1/__scratch__/{org.slug}/scratch/")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"results", "next", "previous"}


@pytest.mark.parametrize(
    ("path", "status_code", "code"),
    [
        ("conflict", 409, "already_accepted"),
        ("payment-required", 402, "SEAT_LIMIT_EXCEEDED"),
        ("unprocessable", 422, "invalid_state_transition"),
    ],
)
def test_domain_errors_produce_the_standard_envelope(org_and_member, path, status_code, code):
    org, user, _membership = org_and_member
    client = Client()
    client.force_login(user)

    response = client.get(f"/api/v1/__scratch__/{org.slug}/scratch/{path}/")

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code


def test_pydantic_validation_error_maps_to_validation_error_envelope(org_and_member):
    org, user, _membership = org_and_member
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/v1/__scratch__/{org.slug}/scratch/echo/",
        data={},
        content_type="application/json",
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["field"] == "name"


def test_authenticated_write_without_csrf_token_gets_401_authentication_failed(org_and_member):
    org, user, _membership = org_and_member
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.post(
        f"/api/v1/__scratch__/{org.slug}/scratch/echo/",
        data={"name": "x"},
        content_type="application/json",
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


@override_settings(KEEL_API_THROTTLE_USER_RATE="1/min")
def test_exceeding_the_user_rate_returns_429_with_retry_after(org_and_member):
    org, user, _membership = org_and_member
    client = Client()
    client.force_login(user)

    first = client.get(f"/api/v1/__scratch__/{org.slug}/scratch/")
    second = client.get(f"/api/v1/__scratch__/{org.slug}/scratch/")

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second
    assert int(second["Retry-After"]) > 0
    assert second.json()["error"]["code"] == "throttled"
