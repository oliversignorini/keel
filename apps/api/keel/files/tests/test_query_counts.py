"""Query-count regression test for ``GET /orgs/<slug>/files/`` (Phase
16.A — docs/query-patterns.md)."""

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.files.tests.factories import file_upload_factory
from keel.organizations import services as org_services

pytestmark = pytest.mark.django_db


def test_list_files_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    org = org_services.create_organization(name="Acme", slug="acme", actor=owner)
    for _ in range(3):
        file_upload_factory(org)

    client = Client()
    client.force_login(owner)

    # 1: session -> session_key. 2: session_key -> User. 3: resolve
    # org_slug -> Organization via active Membership. 4: has_perm's
    # Membership+Role lookup for FILES_VIEW. 5: the file list,
    # select_related("uploader") — one query regardless of row count.
    with django_assert_num_queries(5):  # type: ignore[operator]
        response = client.get(f"/api/v1/orgs/{org.slug}/files/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3
