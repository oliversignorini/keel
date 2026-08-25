"""Tier 1 task shim (PRD §4 invariant 5, "Where does async work run?").

Mirrors Django 6's ``django.tasks`` surface (``@task`` / ``.enqueue()``)
while executing on Celery, so this class of fire-and-forget work is
portable without touching call sites.

**Tier 1 only.** Single-step work that either succeeds or retries: send
an email, sync a Stripe object, run a nightly rollup. Do NOT extend this
to cover multi-step jobs — chaining, per-queue routing, custom task base
classes, step-level commits belong to Celery's actual surface, used
directly. Phase 5.5 builds the Tier 2 primitive properly; growing this
shim to reach it turns a seam into a wall.

Retry/dead-letter policy (PRD §5, docs/plans/phase-5.md 5.3): exponential
backoff with jitter, five attempts, then a ``FailedTask`` row plus a
Sentry event. ``keel.jobs`` is imported lazily inside the failure path
only — every other module in this file's import graph runs on every
request, and ``FailedTask`` is only ever needed on the (rare) dead-letter
path.
"""

import logging
import random
import traceback as traceback_module
from collections.abc import Callable
from typing import Any

from celery import shared_task
from celery.result import EagerResult

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 5
JITTER_FRACTION = 0.25


def report_to_sentry(task_name: str, error: str, traceback_text: str) -> None:
    """Seam for Sentry (PRD §5: "then a FailedTask row plus a Sentry
    event"). Sentry itself is Phase 8 — this is a documented no-op until
    then, same pattern as ``keel.billing.tasks._report_to_sentry``."""


def _backoff_seconds(retries: int) -> float:
    base = float(BASE_BACKOFF_SECONDS * (2**retries))
    return base + random.uniform(0, base * JITTER_FRACTION)


class Task:
    """Wraps a plain function as a Celery task with the shim's fixed
    retry/dead-letter policy. ``func`` stays callable directly (for tests
    and for synchronous call sites) via ``__call__``; ``.enqueue()`` is
    the only way onto Celery."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func
        self.name = f"{func.__module__}.{func.__qualname__}"

        # A free function, not a bound method: celery's ``bind=True``
        # inspects the wrapped callable's own signature to decide where
        # to inject the task instance, and a bound method already has
        # its first (``self``) slot consumed, which throws that
        # inspection off. Closing over ``self`` (this ``Task`` wrapper,
        # not celery's) sidesteps that entirely.
        wrapper = self

        def _run(celery_task: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return wrapper.func(*args, **kwargs)
            except Exception as exc:
                if celery_task.request.retries >= MAX_RETRIES:
                    wrapper._dead_letter(exc, args, kwargs)
                    return None
                raise celery_task.retry(
                    exc=exc, countdown=_backoff_seconds(celery_task.request.retries)
                ) from exc

        self._celery_task = shared_task(
            bind=True,
            max_retries=MAX_RETRIES,
            name=self.name,
        )(_run)

    def _dead_letter(self, exc: Exception, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        from keel.jobs.models import FailedTask

        traceback_text = "".join(
            traceback_module.format_exception(type(exc), exc, exc.__traceback__)
        )
        FailedTask.objects.create(
            task_name=self.name,
            args={"args": list(args), "kwargs": kwargs},
            error=str(exc),
            traceback=traceback_text,
            attempts=MAX_RETRIES,
        )
        report_to_sentry(self.name, str(exc), traceback_text)
        logger.error("task %s dead-lettered after %s attempts", self.name, MAX_RETRIES)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)

    def enqueue(self, *args: Any, **kwargs: Any) -> EagerResult:
        return self._celery_task.delay(*args, **kwargs)


def task(func: Callable[..., Any]) -> Task:
    return Task(func)


def redrive(failed_task_id: Any) -> None:
    """Re-enqueue a dead-lettered task by id (PRD §5: "re-drivable from
    Django admin"). Looks the task up in Celery's own registry by the
    name stored on the ``FailedTask`` row — every task registered through
    this shim is named after its dotted path (see ``Task.__init__``), so
    the row alone is enough to find and re-run it."""
    from celery import current_app

    from keel.jobs.models import FailedTask

    failed_task = FailedTask.objects.get(pk=failed_task_id)
    celery_task = current_app.tasks[failed_task.task_name]
    args = failed_task.args.get("args", [])
    kwargs = failed_task.args.get("kwargs", {})
    celery_task.delay(*args, **kwargs)

    from django.utils import timezone

    failed_task.redriven_at = timezone.now()
    failed_task.save(update_fields=["redriven_at"])
