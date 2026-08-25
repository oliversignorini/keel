"""Dead-letter redrive in Django admin (PRD §5.5.7). ``FailedTaskAdmin``
itself is Phase 5 scaffolding (``keel/jobs/admin.py``) — this is the
test Phase 5 left for it, exercised here against a job task's own
dead-letter row rather than a generic shim task."""

from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from keel.jobs.admin import FailedTaskAdmin
from keel.jobs.models import FailedTask, Job
from keel.jobs.registry import JobStepSpec, JobTypeSpec, registry
from keel.jobs.runner import run_job_task

pytestmark = pytest.mark.django_db


def test_redrive_selected_reenqueues_dead_lettered_job_tasks(settings) -> None:
    from keel.billing.tests.factories import make_organization, make_user

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False

    spec = JobTypeSpec(
        type="t.admin-redrive",
        queue="default",
        credit_estimate=1,
        steps=(JobStepSpec(name="a", run=lambda ctx: "ok"),),
    )
    registry.register(spec)
    try:
        org = make_organization()
        job = Job.objects.create(organization=org, type="t.admin-redrive", requested_by=make_user())

        with (
            patch("keel.jobs.runner.run_job", side_effect=RuntimeError("boom")),
            patch("keel.jobs.runner._backoff_seconds", return_value=0),
        ):
            run_job_task.delay(str(job.id))

        failed = FailedTask.objects.get()
        assert failed.redriven_at is None

        admin = FailedTaskAdmin(FailedTask, AdminSite())
        request = RequestFactory().post("/admin/jobs/failedtask/")
        request.user = make_user()

        with patch.object(admin, "message_user"):
            admin.redrive_selected(request, FailedTask.objects.filter(pk=failed.pk))

        failed.refresh_from_db()
        assert failed.redriven_at is not None

        job.refresh_from_db()
        assert job.status == Job.STATUS_SUCCEEDED
    finally:
        del registry._specs[spec.type]
