"""Query-count regression test for ``GET /orgs/<slug>/__resources__/``
(docs/query-patterns.md explains the methodology). The count is pinned and
commented so a future N+1 fails loudly instead of silently degrading with
row count.

If you add a relation to ``__Resource__``, add it to
``selectors.list___resources__``'s ``select_related`` — not to this
number.
"""

import pytest
from django.test import Client

from keel.__app__.tests.factories import __resource___factory
from keel.accounts.models import User
from keel.organizations import services as org_services

pytestmark = pytest.mark.django_db


def test_list___resources___query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    org = org_services.create_organization(name="Acme", slug="acme", actor=owner)
    for _ in range(3):
        __resource___factory(org)

    client = Client()
    client.force_login(owner)

    # 1: session -> session_key lookup (session_auth).
    # 2: session_key -> User (session_auth).
    # 3: resolve_and_authorize's org_slug -> Organization, joined through
    #    an active Membership (the tenant-isolation lookup).
    # 4: has_perm's Membership+Role lookup for the view code.
    # 5: the list itself, select_related(...) — one query regardless of
    #    row count, which is what this test guards.
    with django_assert_num_queries(5):  # type: ignore[operator]
        response = client.get(f"/api/v1/orgs/{org.slug}/__resources__/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3
