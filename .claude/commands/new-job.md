Generate a job type for `$ARGUMENTS` — a name and, if given, a rough step
list. First decide the tier (PRD §4 invariant 5):

- **Tier 1** (single step, fire-and-forget, succeeds or retries — an
  email, a sync, a rollup): this is not a job, it's a task. Add a
  function to the resource's own `tasks.py` decorated `@task` from
  `keel.core.tasks`, one line delegating to a service. Stop here.
- **Tier 2** (multi-step, resumable, streams progress, can partially
  succeed): use `keel/jobs/`, below. **Ask** if it isn't clear which tier
  fits — extending the Tier-1 shim to cover Tier-2 work is the specific
  mistake `keel/core/tasks.py`'s docstring warns against.

## Tier 2 — `keel/jobs/`

Follow the shape in `keel/jobs/demo.py`.

1. Define each step as a function taking a `StepContext`
   (`keel.jobs.registry`) and returning a small JSON-serialisable value
   or `None`.
2. Register a `JobTypeSpec(type=..., queue=..., credit_estimate=...,
steps=(...))` at import time in a module under the owning app (or
   `keel/jobs/` itself if the job doesn't belong to one domain app).
   Pick `queue` from the four cost-profile queues (`default`, `email`,
   `external`, `scheduled`) — never invent a fifth without checking
   `keel/jobs/` for the routing config.
3. Wire creation through `keel/jobs/services.py`'s job-creation service —
   don't hand-roll `Job`/`JobStep` row creation elsewhere.
4. If the job needs per-tenant concurrency limits, use
   `keel/jobs/concurrency.py`'s existing primitive rather than adding a
   new lock.
5. If progress needs to reach the browser live, use `keel/jobs/sse.py` /
   `keel/jobs/pubsub.py` — don't add polling.

## Permissions

Jobs of a new domain need view/create codes the same way a resource does
— see `Perm.JOBS_VIEW` / `Perm.JOBS_CREATE` for the existing pattern, or
add `/new-permission` codes scoped to this job type if it needs finer
control than "can create any job".

## Tests

- Unit test each step function directly against a `StepContext`.
- A resumption test: run partway, simulate a crash (raise inside a
  step), assert restarting picks up from the right step, not step 1.
- Idempotency: run the same step twice, assert no duplicate side effect
  (`keel/jobs/idempotency.py`).

## Finish

`/check-invariants` — job code is regular service code for invariant 7
(audit) purposes if it writes anything outside the job/step rows
themselves.
