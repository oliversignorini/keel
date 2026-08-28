"""Database-level guarantees and the provenance hook (the
smallest thing that answers what produced this row, from what input,
by which job run)."""

import pytest
from django.db import IntegrityError

from keel.billing.tests.factories import make_organization, make_user
from keel.jobs.demo import DEMO_JOB_TYPE
from keel.jobs.models import Job, JobArtifact, JobStep
from keel.jobs.runner import run_job

pytestmark = pytest.mark.django_db


def _job(organization) -> Job:
    return Job.objects.create(
        organization=organization, type=DEMO_JOB_TYPE, requested_by=make_user()
    )


def test_jobstep_ordinal_is_unique_per_job() -> None:
    job = _job(make_organization())
    JobStep.objects.create(job=job, ordinal=0, name="a")
    with pytest.raises(IntegrityError):
        JobStep.objects.create(job=job, ordinal=0, name="a-again")


def test_the_same_ordinal_is_allowed_across_different_jobs() -> None:
    org = make_organization()
    first, second = _job(org), _job(org)
    JobStep.objects.create(job=first, ordinal=0, name="a")
    JobStep.objects.create(job=second, ordinal=0, name="a")  # must not raise


def test_running_the_demo_job_writes_a_provenance_carrying_artifact() -> None:
    org = make_organization()
    job = _job(org)
    run_job(job.id)

    artifact = JobArtifact.objects.get(organization=org, kind="demo.count")
    assert artifact.produced_by_job_id == job.id
    assert artifact.produced_by_input_ref
    assert artifact.value == {"count": 0}


def test_provenance_survives_the_job_being_deleted() -> None:
    """``produced_by_job`` is ``SET_NULL`` — the produced row is a durable
    record; the job it names is transient bookkeeping."""
    org = make_organization()
    job = _job(org)
    run_job(job.id)
    artifact = JobArtifact.objects.get(organization=org, kind="demo.count")

    job.delete()

    artifact.refresh_from_db()
    assert artifact.produced_by_job_id is None
