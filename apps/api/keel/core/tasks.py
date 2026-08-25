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
"""

from collections.abc import Callable
from typing import Any

from celery import shared_task
from celery.result import EagerResult


class Task:
    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func
        self._celery_task = shared_task(func)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)

    def enqueue(self, *args: Any, **kwargs: Any) -> EagerResult:
        return self._celery_task.delay(*args, **kwargs)


def task(func: Callable[..., Any]) -> Task:
    return Task(func)
