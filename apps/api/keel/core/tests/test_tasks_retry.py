"""Retry, dead-letter, redrive (PRD §5; docs/plans/phase-5.md 5.3)."""

from unittest.mock import patch

import pytest

from keel.core.tasks import MAX_RETRIES, redrive, task
from keel.jobs.models import FailedTask


@pytest.mark.django_db
def test_a_task_that_always_succeeds_never_retries_or_dead_letters(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    calls = []

    @task
    def always_ok(value):
        calls.append(value)

    always_ok.enqueue(1)

    assert calls == [1]
    assert FailedTask.objects.count() == 0


@pytest.mark.django_db
def test_a_task_that_always_raises_retries_five_times_then_dead_letters(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    attempts = []

    @task
    def always_fails(organization_id: str) -> None:
        attempts.append(organization_id)
        raise ValueError("boom")

    with patch("keel.core.tasks._backoff_seconds", return_value=0):
        always_fails.enqueue("org-1")

    # One initial attempt plus MAX_RETRIES retries, all eager.
    assert len(attempts) == MAX_RETRIES + 1

    failed = FailedTask.objects.get()
    assert failed.task_name.endswith("always_fails")
    assert failed.attempts == MAX_RETRIES
    assert "boom" in failed.error
    assert failed.args == {"args": ["org-1"], "kwargs": {}}
    assert failed.redriven_at is None


@pytest.mark.django_db
def test_a_task_that_fails_then_succeeds_retries_and_recovers(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    attempts = []

    @task
    def flaky(value):
        attempts.append(value)
        if len(attempts) < 2:
            raise ValueError("not yet")
        return value

    with patch("keel.core.tasks._backoff_seconds", return_value=0):
        flaky.enqueue("x")

    assert len(attempts) == 2
    assert FailedTask.objects.count() == 0


@pytest.mark.django_db
def test_redrive_re_enqueues_the_dead_lettered_task_and_marks_it_redriven(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    attempts = []

    @task
    def sometimes_fails(value):
        attempts.append(value)
        if len(attempts) == 1:
            raise ValueError("boom")
        return value

    with (
        patch("keel.core.tasks._backoff_seconds", return_value=0),
        patch("keel.core.tasks.MAX_RETRIES", 0),
    ):
        sometimes_fails.enqueue("y")

    failed = FailedTask.objects.get()
    assert failed.redriven_at is None

    redrive(failed.pk)

    failed.refresh_from_db()
    assert failed.redriven_at is not None
    assert attempts == ["y", "y"]
