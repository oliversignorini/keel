"""Meta-test (PRD §5): every Tier-1 ``@task``
in the project has a single-service-call body and takes ids, never model
instances — and the checks in ``keel.core.lint_tasks`` actually catch a
deliberate violation of each, not just pass vacuously on real code."""

import pytest
from django.db import models

from keel.core.lint_tasks import (
    TaskLintViolation,
    check_single_service_call,
    check_takes_ids_not_instances,
    check_task,
    discover_shim_tasks,
)
from keel.core.tasks import task


def test_every_shim_task_in_the_project_passes_both_checks() -> None:
    shim_tasks = list(discover_shim_tasks("keel"))
    assert shim_tasks, "no @task-decorated tasks found — the discovery walk is broken"
    for shim_task in shim_tasks:
        check_task(shim_task)  # raises TaskLintViolation on failure


def test_single_service_call_check_catches_a_multi_statement_body() -> None:
    @task
    def violates_single_call(organization_id: str) -> None:
        print(organization_id)
        print(organization_id)

    with pytest.raises(TaskLintViolation, match="exactly one service call"):
        check_single_service_call(violates_single_call)


def test_single_service_call_check_passes_a_lookup_then_one_call() -> None:
    @task
    def compliant(value_id: str) -> None:
        print(value_id)

    check_single_service_call(compliant)  # does not raise


class _FixtureModel(models.Model):
    """A stand-in Model subclass, purely so the annotation check below
    has something real (``issubclass(hint, models.Model)``) to catch —
    never migrated, never saved."""

    class Meta:
        app_label = "core"

    def __str__(self) -> str:
        return "fixture model"


def test_ids_not_instances_check_catches_a_model_instance_parameter() -> None:
    @task
    def violates_ids_only(instance: _FixtureModel) -> None:
        print(instance)

    with pytest.raises(TaskLintViolation, match="Model subclass"):
        check_takes_ids_not_instances(violates_ids_only)


def test_ids_not_instances_check_passes_a_plain_id_parameter() -> None:
    @task
    def takes_an_id(organization_id: str) -> None:
        print(organization_id)

    check_takes_ids_not_instances(takes_an_id)  # does not raise
