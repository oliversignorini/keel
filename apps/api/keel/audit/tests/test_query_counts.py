"""Query-count regression test for ``GET /orgs/<slug>/audit/`` (Phase
16.A — docs/query-patterns.md)."""

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.audit.tests.factories import audit_log_factory
from keel.organizations import services as org_services

pytestmark = pytest.mark.django_db


def test_list_audit_logs_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    org = org_services.create_organization(name="Acme", slug="acme", actor=owner)
    # create_organization itself writes an audit row (@audited) — three
    # more on top of that exercises the select_related with several rows.
    for _ in range(3):
        audit_log_factory(org)

    client = Client()
    client.force_login(owner)

    # 1: session -> session_key. 2: session_key -> User. 3: resolve
    # org_slug -> Organization via active Membership. 4: has_perm's
    # Membership+Role lookup for AUDIT_VIEW. 5: the audit log list,
    # select_related("actor", "impersonator") — one query regardless of
    # row count.
    with django_assert_num_queries(5):  # type: ignore[operator]
        response = client.get(f"/api/v1/orgs/{org.slug}/audit/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 4
