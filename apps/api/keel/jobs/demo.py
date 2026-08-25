"""The demo job type (PRD §5.5.7; docs/plans/phase-5.5.md 5.5.7) — three
steps, kept in its own module (registered from ``keel.jobs.apps.JobsConfig
.ready()``) so it can be lifted straight off the ``init`` removal list
alongside the rest of the demo resource (``keel/widgets/``) without
touching anything else in ``keel/jobs``. Nothing in this app imports
this module except ``apps.py``.
"""

from __future__ import annotations

from keel.jobs.registry import JobStepSpec, JobTypeSpec, StepContext, registry

DEMO_JOB_TYPE = "demo.count_items"


def _step_prepare(context: StepContext) -> str:
    return "prepared"


def _step_count(context: StepContext) -> int:
    items = context.params.get("items", [])
    return len(items)


def _step_finish(context: StepContext) -> str:
    return "done"


registry.register(
    JobTypeSpec(
        type=DEMO_JOB_TYPE,
        queue="default",
        credit_estimate=3,
        steps=(
            JobStepSpec(name="prepare", run=_step_prepare),
            JobStepSpec(name="count", run=_step_count),
            JobStepSpec(name="finish", run=_step_finish),
        ),
    )
)
