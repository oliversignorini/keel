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
    from keel.jobs.models import JobArtifact

    items = context.params.get("items", [])
    count = len(items)
    # Demonstrates the provenance hook (keel.core.models.ProvenanceMixin)
    # against a real produced record: this row carries the job that made
    # it and a description of the input it was derived from, without
    # JobArtifact or this step needing anything beyond what StepContext
    # already gives every step.
    JobArtifact.objects.create(
        organization_id=context.organization_id,
        produced_by_job_id=context.job_id,
        produced_by_input_ref=f"params.items[{count}]",
        kind="demo.count",
        value={"count": count},
    )
    return count


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
