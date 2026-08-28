"""Query-count regression tests for ``GET /me/``, ``GET /orgs/`` and
``GET /orgs/<slug>/members/`` (Phase 16.A — docs/query-patterns.md)."""

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.organizations import services as org_services
from keel.organizations.tests.factories import membership_factory

pytestmark = pytest.mark.django_db


def _client_for(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def test_me_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    for i in range(3):
        org_services.create_organization(name=f"Org {i}", slug=f"org-{i}", created_by=owner)

    client = _client_for(owner)

    # 1: session -> session_key. 2: session_key -> User. 3: the user's
    # organisations (``list_organizations_for_user``). 4: every one of
    # those organisations' active membership + role, in one
    # ``organization__in`` query (api-patterns finding 12 — this used to
    # be one query per organisation). 5: entitlements resolved in bulk
    # for every organisation (``resolve_entitlements_bulk``) — one query
    # regardless of how many organisations the user belongs to.
    with django_assert_num_queries(5):  # type: ignore[operator]
        response = client.get("/api/v1/me/")
    assert response.status_code == 200
    assert len(response.json()["organizations"]) == 3


def test_list_organizations_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    for i in range(3):
        org_services.create_organization(name=f"Org {i}", slug=f"org-{i}", created_by=owner)

    client = _client_for(owner)

    # 1: session -> session_key. 2: session_key -> User. 3: the
    # organisation list itself — one query regardless of row count.
    with django_assert_num_queries(3):  # type: ignore[operator]
        response = client.get("/api/v1/orgs/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3


def test_list_members_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    org = org_services.create_organization(name="Acme", slug="acme", created_by=owner)
    for _ in range(3):
        membership_factory(org)

    client = _client_for(owner)

    # 1: session -> session_key. 2: session_key -> User. 3: resolve
    # org_slug -> Organization via active Membership. 4: has_perm's
    # Membership+Role lookup for MEMBERS_VIEW. 5: the member list,
    # select_related("user", "role") — one query regardless of row count.
    with django_assert_num_queries(5):  # type: ignore[operator]
        response = client.get(f"/api/v1/orgs/{org.slug}/members/")
    assert response.status_code == 200
    # +1 for the owner's own membership created by create_organization.
    assert len(response.json()["results"]) == 4
