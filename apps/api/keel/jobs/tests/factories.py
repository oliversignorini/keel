"""Row builders for jobs tests, plus ``JobResource.test_factory``'s target
(PRD §4 invariant 7 — the cross-org meta-test walk)."""

from django.utils.crypto import get_random_string

from keel.accounts.models import User
from keel.jobs.demo import DEMO_JOB_TYPE
from keel.jobs.models import Job
from keel.organizations.models import Organization


def _requester(organization: Organization) -> User:
    return User.objects.create_user(
        email=f"jobs-{organization.pk}-{get_random_string(6).lower()}@example.com",
        password="s3cret-pass",
    )


def job_factory(organization: Organization) -> Job:
    return Job.objects.create(
        organization=organization,
        type=DEMO_JOB_TYPE,
        requested_by=_requester(organization),
        params={"items": [1, 2, 3]},
    )
