"""__Resource__ job type (CLAUDE.md invariant 5, Tier 2 — multi-step,
resumable, streams progress, can partially succeed). Registered from
``keel.jobs.apps.JobsConfig.ready()``; nothing else should import this
module directly (see ``keel/jobs/demo.py`` for the shape this was copied
from).

Wire creation through ``keel.jobs.services``'s job-creation service — don't
hand-roll ``Job``/``JobStep`` row creation elsewhere. If this job needs
per-tenant concurrency limits, use ``keel.jobs.concurrency``'s existing
primitive; if progress needs to reach the browser live, use
``keel.jobs.sse`` / ``keel.jobs.pubsub`` instead of polling — neither is
wired here, both are judgement.
"""

from __future__ import annotations

from keel.jobs.registry import JobStepSpec, JobTypeSpec, StepContext, registry

__RESOURCE___JOB_TYPE = "__resource__"


# keel:insert step_functions


registry.register(
    JobTypeSpec(
        type=__RESOURCE___JOB_TYPE,
        queue="default",
        credit_estimate=1,
        steps=(
            # keel:insert step_specs
        ),
    )
)
