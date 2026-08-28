"""Query-count regression test for ``GET /orgs/<slug>/widgets/`` (Phase
16.A — docs/query-patterns.md explains the methodology). The count is
pinned and commented so a future N+1 fails loudly instead of silently
degrading with row count.
"""

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.organizations import services as org_services
from keel.widgets.tests.factories import widget_factory

pytestmark = pytest.mark.django_db


def test_list_widgets_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    org = org_services.create_organization(name="Acme", slug="acme", created_by=owner)
    for _ in range(3):
        widget_factory(org)

    client = Client()
    client.force_login(owner)

    # 1: session -> session_key lookup (session_auth).
    # 2: session_key -> User (session_auth).
    # 3: resolve_and_authorize's org_slug -> Organization, joined through
    #    an active Membership (the tenant-isolation lookup).
    # 4: has_perm's Membership+Role lookup for WIDGETS_VIEW.
    # 5: the widget list itself, select_related("created_by") — one query
    #    regardless of row count, which is what this test guards.
    with django_assert_num_queries(5):  # type: ignore[operator]
        response = client.get(f"/api/v1/orgs/{org.slug}/widgets/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3
