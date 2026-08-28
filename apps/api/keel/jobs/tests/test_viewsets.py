"""``orgs/<org_slug>/jobs/`` end to end (PRD §7).

``pytest.mark.django_db`` (not ``transaction=True``) wraps each test in
a transaction that is rolled back, never committed — which means
``transaction.on_commit()`` never fires unless a test opts in via
``django_capture_on_commit_callbacks``. Most tests below deliberately
do *not* opt in: that is what lets "returns 202 with the work not yet
started" (PRD §5.5.5 acceptance) be asserted without mocking anything —
the job genuinely has not been picked up by a worker yet, the same as
in production between the response and the broker delivering the task.
"""

import time

import pytest
from django.test import Client

from keel.accounts.models import User
from keel.jobs.demo import DEMO_JOB_TYPE
from keel.jobs.models import Job
from keel.organizations import services
from keel.organizations.models import Membership, Role
from keel.organizations.permissions import Perm

pytestmark = pytest.mark.django_db

_counter = 0


def _user(prefix: str = "user") -> User:
    global _counter
    _counter += 1
    return User.objects.create_user(
        email=f"{prefix}-{_counter}@example.com", password="s3cret-pass"
    )


def _client_for(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _org_with_owner():
    global _counter
    _counter += 1
    creator = _user("owner")
    org = services.create_organization(
        name="Acme", slug=f"acme-jobs-{_counter}", created_by=creator
    )
    return org, creator


def test_create_job_returns_202_quickly_with_the_work_not_yet_started() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    # A cold Python process's very first request pays a one-time cost
    # (URLconf resolution, first-import of every view module the
    # urlconf touches) that has nothing to do with this route's own
    # latency — warm it up first so the timed request below measures
    # steady-state job creation, the thing this test actually asserts.
    client.get(f"/api/v1/orgs/{org.slug}/jobs/")

    started = time.perf_counter()
    response = client.post(
        f"/api/v1/orgs/{org.slug}/jobs/",
        {"type": DEMO_JOB_TYPE, "params": {"items": [1]}},
        content_type="application/json",
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert response.status_code == 202, response.json()
    body = response.json()
    assert body["status"] == Job.STATUS_QUEUED
    assert elapsed_ms < 300, f"POST took {elapsed_ms:.1f}ms"

    job = Job.objects.get(pk=body["id"])
    assert job.status == Job.STATUS_QUEUED
    assert job.started_at is None


def test_replaying_the_same_idempotency_key_over_http_returns_the_original_job() -> None:
    org, owner = _org_with_owner()
    client = _client_for(owner)

    first = client.post(
        f"/api/v1/orgs/{org.slug}/jobs/",
        {"type": DEMO_JOB_TYPE},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="replay-key-1",
    )
    second = client.post(
        f"/api/v1/orgs/{org.slug}/jobs/",
        {"type": DEMO_JOB_TYPE},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="replay-key-1",
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert Job.objects.filter(organization=org).count() == 1


def test_list_jobs_filterable_by_status() -> None:
    org, owner = _org_with_owner()
    Job.objects.create(
        organization=org, type=DEMO_JOB_TYPE, requested_by=owner, status=Job.STATUS_QUEUED
    )
    Job.objects.create(
        organization=org, type=DEMO_JOB_TYPE, requested_by=owner, status=Job.STATUS_SUCCEEDED
    )
    client = _client_for(owner)

    response = client.get(f"/api/v1/orgs/{org.slug}/jobs/?status=succeeded")

    assert response.status_code == 200
    statuses = [row["status"] for row in response.json()["results"]]
    assert statuses == [Job.STATUS_SUCCEEDED]


def test_retrieve_a_job_includes_its_steps() -> None:
    org, owner = _org_with_owner()
    job = Job.objects.create(organization=org, type=DEMO_JOB_TYPE, requested_by=owner)
    job.steps.create(name="a", ordinal=0, status=Job.STATUS_SUCCEEDED)
    client = _client_for(owner)

    response = client.get(f"/api/v1/orgs/{org.slug}/jobs/{job.id}/")

    assert response.status_code == 200
    assert len(response.json()["steps"]) == 1


def test_cancel_marks_a_queued_job_failed() -> None:
    org, owner = _org_with_owner()
    job = Job.objects.create(organization=org, type=DEMO_JOB_TYPE, requested_by=owner)
    client = _client_for(owner)

    response = client.post(f"/api/v1/orgs/{org.slug}/jobs/{job.id}/cancel/")

    assert response.status_code == 200
    assert response.json()["status"] == Job.STATUS_FAILED


def test_a_member_without_jobs_create_is_denied_with_a_reason() -> None:
    org, _owner = _org_with_owner()
    powerless_role = Role.objects.create(organization=org, name="Powerless", permissions=[])
    member = _user("member")
    Membership.objects.create(
        organization=org, user=member, role=powerless_role, status=Membership.STATUS_ACTIVE
    )
    client = _client_for(member)

    response = client.post(
        f"/api/v1/orgs/{org.slug}/jobs/",
        {"type": DEMO_JOB_TYPE},
        content_type="application/json",
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "insufficient_role"
    assert body["error"]["denial"]["required"] == Perm.JOBS_CREATE


def test_cross_organization_job_access_404s() -> None:
    org_a, owner_a = _org_with_owner()
    org_b, _owner_b = _org_with_owner()
    job = Job.objects.create(organization=org_a, type=DEMO_JOB_TYPE, requested_by=owner_a)
    client = _client_for(owner_a)

    response = client.get(f"/api/v1/orgs/{org_b.slug}/jobs/{job.id}/")

    assert response.status_code == 404
