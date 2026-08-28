"""Query-count regression test for ``GET /orgs/<slug>/jobs/`` (Phase
16.A — docs/query-patterns.md). Each job carries ``JobStep`` rows
(``JobOut.resolve_steps`` reads ``obj.steps.all()``), so this also guards
the ``steps`` prefetch: without it, this test's query count would grow
with the number of jobs, not stay fixed."""

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.jobs.models import JobStep
from keel.jobs.tests.factories import job_factory
from keel.organizations import services as org_services

pytestmark = pytest.mark.django_db


def test_list_jobs_query_count(django_assert_num_queries: object) -> None:
    owner = User.objects.create_user(email="owner@example.com", password="s3cret-pass")
    org = org_services.create_organization(name="Acme", slug="acme", created_by=owner)
    for _ in range(3):
        job = job_factory(org)
        JobStep.objects.create(job=job, name="step-1", ordinal=0)

    client = Client()
    client.force_login(owner)

    # 1: session -> session_key. 2: session_key -> User. 3: resolve
    # org_slug -> Organization via active Membership. 4: has_perm's
    # Membership+Role lookup for JOBS_VIEW. 5: the job list itself.
    # 6: the prefetch_related("steps") query — one query total for every
    # job's steps, not one per job.
    with django_assert_num_queries(6):  # type: ignore[operator]
        response = client.get(f"/api/v1/orgs/{org.slug}/jobs/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3
