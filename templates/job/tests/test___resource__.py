"""Tests for the __Resource__ job type (docs/plans/phase-19.md 19.B).

Every generated step is a stub (``return None``) — business logic is
judgement, left for whoever fills in ``keel/jobs/__resource__.py``. What
this file proves mechanically: each step is callable against a
``StepContext``, a job of this type resumes after a simulated worker kill
without re-running a step that already succeeded, and running the same job
twice does not fork its step set (CLAUDE.md invariant 5's "resumable" and
"idempotent" halves).
"""

import pytest

# keel:insert job_type_import
from keel.billing.tests.factories import make_organization
from keel.jobs.models import Job, JobStep
from keel.jobs.registry import StepContext
from keel.jobs.runner import run_job

pytestmark = pytest.mark.django_db

# keel:insert step_names_tuple


def _job(organization) -> Job:
    return Job.objects.create(
        organization=organization,
        type=__RESOURCE___JOB_TYPE,
        requested_by=organization.created_by,
        step_count=len(_STEP_NAMES),
    )


# keel:insert step_unit_tests


def test_resuming_after_a_simulated_worker_kill_skips_the_completed_step() -> None:
    org = make_organization()
    job = _job(org)

    # First run "crashes" after the first step: pre-create its succeeded
    # row, exactly as a restarted worker would find it, then call
    # run_job again.
    JobStep.objects.create(
        job=job, ordinal=0, name=_STEP_NAMES[0], status=Job.STATUS_SUCCEEDED, output_ref="done"
    )

    run_job(job.id)

    job.refresh_from_db()
    assert job.status == Job.STATUS_SUCCEEDED
    first_step = job.steps.get(ordinal=0)
    # Untouched: still the pre-seeded value, not whatever the step itself
    # would have produced.
    assert first_step.output_ref == "done"


def test_running_the_same_job_twice_does_not_fork_its_step_set() -> None:
    org = make_organization()
    job = _job(org)

    run_job(job.id)
    run_job(job.id)

    job.refresh_from_db()
    assert job.status == Job.STATUS_SUCCEEDED
    assert job.steps.count() == len(_STEP_NAMES)
