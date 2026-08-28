"""Meta-test (docs/plans/phase-16.md 16.C "async boundary"): every Tier-2
Celery ``@shared_task`` in the project takes ids, never model instances —
the one PRD §5 acceptance criterion that applies regardless of tier.
``discover_shim_tasks``/``check_takes_ids_not_instances``
(``keel.core.lint_tasks``, exercised by ``test_meta_task_lint.py``) only
ever walked Tier-1 ``@task``-shim functions; Tier-2 tasks
(``keel.billing.tasks.dispatch_stripe_event``,
``keel.jobs.runner.run_job_task``, and friends) had no automated check at
all before this — see docs/boundary-guardrails.md "Async boundary"."""

import pytest

from keel.core.lint_tasks import (
    TaskLintViolation,
    check_shared_task_takes_ids_not_instances,
    discover_shared_tasks,
)


def test_every_shared_task_in_the_project_takes_ids_not_instances() -> None:
    shared_tasks = list(discover_shared_tasks("keel"))
    assert shared_tasks, "no @shared_task-decorated tasks found — the discovery walk is broken"
    for shared_task in shared_tasks:
        # raises TaskLintViolation on failure
        check_shared_task_takes_ids_not_instances(shared_task)


def test_check_catches_a_model_instance_parameter() -> None:
    from celery import shared_task
    from django.db import models

    class _SharedTaskFixtureModel(models.Model):
        class Meta:
            app_label = "core"

        def __str__(self) -> str:
            return "fixture model"

    @shared_task(name="keel.core.tests.fixture.violates_ids_only")
    def violates_ids_only(instance: _SharedTaskFixtureModel) -> None:
        print(instance)

    with pytest.raises(TaskLintViolation, match="Model subclass"):
        check_shared_task_takes_ids_not_instances(violates_ids_only)


def test_check_passes_a_plain_id_parameter() -> None:
    from celery import shared_task

    @shared_task(name="keel.core.tests.fixture.takes_an_id")
    def takes_an_id(organization_id: str) -> None:
        print(organization_id)

    check_shared_task_takes_ids_not_instances(takes_an_id)  # does not raise
