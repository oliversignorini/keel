# Jobs and audit

What `keel/jobs/` and `keel/audit/` actually guarantee, how to extend
each safely, and where the boundary between "belongs in Keel" and
"belongs in a product built on Keel" sits. This document hardens the
constraints underneath the mechanisms and closes the gaps a design
review found. Read `keel/jobs/*.py`'s and
`keel/audit/*.py`'s own docstrings for the reasoning behind any one
line — this document is the map across files, not a replacement for them.

## What belongs in Keel versus a product

`keel/jobs/` is a resumable async-job runner with per-organisation
concurrency control, idempotent creation, credit-hold settlement, and a
live SSE status stream. What it is deliberately **not**: a specific job.
`keel/jobs/demo.py` (`demo.count_items`) is the only registered job type
in the template, exists purely to exercise the runner end to end, and is
removable — same footprint as `keel/widgets/`, the reference CRUD slice.
A product built on Keel adds its own job types in its own module (see
"Adding a job type" below) and, if it needs one, its own generic-and-cheap
notion of "what produced this row" via `ProvenanceMixin` — Keel does not
know, and must not need to know, what any of those consumers are.

`keel/audit/` is the audit trail: one `AuditLog` row per mutating service
call, written inline in the same transaction as the effect it describes,
readable per organisation behind `audit.view`. What it is not: a
general-purpose event bus, a metrics pipeline, or an approval workflow —
it is a record of "what happened, who did it, and whether they were
impersonating someone," nothing more.

## Adding a job type

1. In your own app (not `keel/jobs/`), write step functions — each
   receives a `keel.jobs.registry.StepContext` (`job_id`,
   `organization_id`, `params`, `results`) and returns a small
   JSON-serialisable value or `None`. A step that needs a prior step's
   real output re-derives it or loads it from wherever it actually
   lives (a file, a row) — `results` only carries what
   `JobStep.output_ref` stored, deliberately opaque past that, because a
   resumed job reads exactly the same thing a fresh one would.
2. Register a `keel.jobs.registry.JobTypeSpec` (`type`, `queue`,
   `credit_estimate`, `steps`) from your app's `AppConfig.ready()` —
   see `keel/jobs/apps.py` registering `keel/jobs/demo.py` for the
   shape.
3. Create jobs through `keel.jobs.services.create_job`, never
   `Job.objects.create()` directly — it is the one place that ties the
   registry, the idempotency guarantee, and the credit hold together.

**Tasks take ids, never model instances.** `run_job(job_id)` and
`run_job_task(job_id)` both take a plain id. Celery serialises task
arguments through its result backend and broker — a passed-in model
instance is pickled/JSON-encoded as of the moment the task was
_enqueued_, and a retried or resumed task re-reads it stale. An id forces
every re-entry (a resumed task, an admin redrive, `sweep_stuck_jobs`
itself) to `.get()` the row fresh, which is exactly what
makes `run_job` safe to call twice.

## Idempotency

`Idempotency-Key` handling lives in `keel/core/idempotency.py` — it
moved out of `keel/jobs/` because it was never actually jobs-specific
(a retried POST can duplicate a Stripe checkout session,
an invitation email, an upload row, or an organisation exactly the way
it can duplicate a job). Two layers, cheapest first:

1. **The cache claim** (`check_and_claim`, or `@idempotent` applied to a
   Ninja view function). A first request with a given key claims a
   Redis cache slot and proceeds; a replay with the same key while the
   first is still in flight gets a `409 Conflict`
   (`idempotency_key_in_progress`) raised through the normal
   `keel.core.exceptions` → `keel.core.error_handlers` envelope
   machinery, not a hand-built response; a replay after the first
   completed gets the cached response replayed verbatim, without the
   view running again. `@idempotent` scopes the cache key by the
   decorated view's own module-qualified name plus `org_slug` (when the
   route has one), so two different endpoints — or the same endpoint
   for two different organisations — never share a key space even if a
   caller reuses a header value by coincidence.
2. **The database constraint.** The cache claim is cheap and closes most
   of the race, but it is not the real guarantee: two requests can both
   pass `cache.get()` before either calls `cache.add()`, and — the gap
   this closes — `create_job`'s own `select_for_update()` locks a
   `Job` row that doesn't exist yet when both requests read `None` for
   the same key, so it cannot serialise them either. `Job` carries a
   partial `UniqueConstraint` on `(organization, idempotency_key)`
   (excluding the empty string, so jobs created without a key never
   collide with each other), and `create_job` catches the resulting
   `IntegrityError` and returns the row the winner of the race actually
   created. This is the pattern to copy for any new idempotency-scoped
   write: cache claim for the common case, a real constraint for the
   case the cache claim cannot cover, caught and resolved to "return the
   existing row," not surfaced as a 500.

Applied to every side-effectful POST worth deduplicating today:
`createJob`, `createCheckoutSession`, `createUpload`, `createInvitation`,
`createOrganization`, `acceptInvite`. `createUpload`'s replay is the one
case worth a second look before copying the pattern blindly: the cached
response includes a presigned URL that expires, so a replay outside the
URL's expiry window returns a link that no longer works — acceptable
today (idempotency here is about not creating a second row, not about
the URL's shelf life), worth revisiting if a product build on this
starts relying on long-lived idempotent replay of upload URLs.

## Concurrency control

`keel/jobs/concurrency.py`'s `OrgConcurrencyLimiter` is a Redis sorted-set
semaphore, one per organisation, that never blocks the calling worker —
`try_acquire` returns `False` immediately when the organisation is at its
limit, and `run_job_task` re-queues its own task a few seconds out
instead of holding a worker slot hostage waiting for the organisation's
turn. Two properties worth knowing before touching this file:

- **Time comes from Redis, not the caller.** The acquire/renew Lua
  script reads `TIME` from Redis itself rather than accepting a
  client-supplied timestamp — a worker with a skewed local clock must
  never get to decide when another worker's slot expires.
- **The lease is renewed at each step boundary**, not just once at
  acquisition. `run_job`'s per-step loop calls `limiter.renew(...)`
  before running each step, so a job whose steps together outlive
  `LEASE_SECONDS` (one hour by default) doesn't silently lose its slot
  partway through and over-admit the organisation for the rest of the
  run. A step function that itself runs long (well past the heartbeat
  interval implied by adjacent steps) is still a gap this doesn't
  close — keep individual steps short relative to the lease, the same
  assumption `STUCK_JOB_THRESHOLD_MINUTES` (the beat sweeper) already
  makes.

Applies to Tier 2 (multi-step, resumable Celery) jobs only — it has
nothing to do with Tier 1 fire-and-forget tasks through
`keel/core/tasks.py`'s shim, which has its own retry/dead-letter policy
and no per-organisation fairness concept at all.

## Job failure, retry, and dead-lettering

- **Retry**: `run_job_task` retries with jittered exponential backoff up
  to `MAX_RETRIES` (five) on any exception from `run_job` itself.
  Concurrency-limiter refusals are a separate, unbounded retry path
  (`self.retry(..., max_retries=None)`) that must never count against
  `MAX_RETRIES` — an organisation being busy is not the job's fault.
- **Dead-lettering**: exhausting `MAX_RETRIES` writes a `FailedTask` row
  (task name, args, error, traceback, attempt count) rather than losing
  the failure silently. Visible and actionable in Django admin
  (`FailedTaskAdmin`) — select rows and use the "Redrive selected failed
  tasks" action, which calls `keel.core.tasks.redrive` per row and
  clears `redriven_at`. `test_admin.py::test_redrive_selected_reenqueues_dead_lettered_job_tasks`
  exercises this end to end against a job task's own dead-letter row.
- **Stuck jobs**: `sweep_stuck_jobs` (a beat task,
  `sweep_stuck_jobs_task`) fails any `Job` still `running`
  `STUCK_JOB_THRESHOLD_MINUTES` (default 60) after `started_at` and
  refunds its credit hold — the backstop for a worker that hangs or is
  killed _after_ the broker's ack, which `task_acks_late` redelivery
  can't recover on its own.
- **Partial success**: a job where some steps succeeded and others
  failed lands in `Job.STATUS_PARTIAL`, not `FAILED` — surfaced in
  `JobOut.status` (a published `Literal`, not a bare `str`) and settled
  proportionally (see credits below).

All of the above is exercised twice each in the test suite: once as a
single call (does the mechanism work), and again as two calls against the
same job (`keel/jobs/tests/test_idempotent_settlement.py`) — Celery is
at-least-once by design, so "ran once" tests alone would pass even if a
redelivery double-settled a credit hold.

## Credits: hold, settle, refund — and why it's idempotent now

`create_job` places a credit **hold** for the job's estimated cost, in
the same transaction as the `Job` row. When the job finishes,
`_settle_credits` either **releases** the unused portion (partial or full
success) or **refunds** the whole hold (nothing succeeded). The property
that makes re-running `run_job` on an already-terminal job safe: the hold
entry is locked with `SELECT ... FOR UPDATE` _before_ checking whether a
`release`/`refund` entry already exists for it — the lock-then-check
order is what stops two concurrent settlement attempts (a retried
delivery racing a cancel, or two retried deliveries) from both reading
"not yet settled" and both writing. `cancel_job` takes the same lock on
the `Job` row itself before re-checking terminal status, for the
symmetric race (two concurrent cancels, or a cancel racing the runner's
own final step).

`Job.step_count` is pinned at creation time from the registry's step
list, and the runner totals against that column, never a live re-read of
`len(spec.steps)` — re-registering a job type with a different step
count (a deploy that ships mid-flight) must not silently re-price a job
that already holds credits based on the old count. `Job.params` also
carries a `_v` version stamp, stored inside the JSON blob itself, for the
same reason on the params side: nothing reads it yet, but the first
breaking change to a job type's params shape has somewhere to check
before assuming an in-flight job's `params` matches the new step code's
expectations.

## SSE: live job status

`GET /orgs/<org_slug>/jobs/stream/` (served by the dedicated ASGI
service — see `config/urls_stream.py`, never the sync gunicorn process)
streams every `job`/`step` transition for the organisation over one
connection. Two things worth knowing about its guarantees:

- **It is at-most-once.** Redis pub/sub has no buffer and no replay — a
  browser tab that's disconnected when an event publishes never
  receives it, full stop. A `seq` addresses this: a per-organisation,
  monotonically increasing counter (`INCR`), stamped on every published
  event. `seq` does not make the stream replayable on its own — there is
  nothing to replay _from_ — but it turns "silently missed an event"
  into "detectable": a reconnecting client compares the `seq` on the
  first event of the new connection against the last one it saw and, on
  any gap, refetches `GET /orgs/<org_slug>/jobs/` (already the source of
  truth for job state) instead of trusting a stream it knows skipped
  something.
- **This is the cheaper of two fixes**, deliberately. The alternative is
  Redis Streams (`XADD`/`XRANGE`, honouring `Last-Event-ID` on
  reconnect) for true resumability — at the cost of a second Redis data
  structure and a retention policy for it. The job tray only ever needs
  "am I looking at current state," which a refetch answers exactly as
  well as a replayed log would; revisit this if a future consumer of
  the stream needs to reconstruct history it missed rather than just
  resynchronise to the present.

The stream is served outside Django Ninja's own routing (a separate ASGI
app), so nothing generates a TypeScript client method for it — declared
by hand in `scripts/merge_openapi.py` instead, so the event shape
(`JobStreamEvent`) is at least part of the published OpenAPI document
even though `EventSource`, not a generated client call, is what actually
consumes it.

## Provenance: what produced this row

Future document-ingestion or data-pipeline work needs to answer "what
produced this row, from what input, by which job run." Rather than build
that (out of scope here — no ingestion pipeline exists yet), this repo
carries the smallest hook that answers it: `ProvenanceMixin`
(`keel/core/models.py`), two nullable columns —

- `produced_by_job`: a string-referenced FK to `jobs.Job`
  (`on_delete=SET_NULL`) — string-referenced the same way
  `OrgScopedModel.organization` points at `organizations.Organization`,
  so a model in any app can inherit this mixin without ever importing
  `keel.jobs`, and `keel.jobs` never imports a single one of its
  consumers.
- `produced_by_input_ref`: a free-form string describing the specific
  input the row was derived from (a source row's id, a file key, a
  params field) — deliberately opaque, because what counts as "the
  input" is a consumer decision this mixin has no business making.

`keel/jobs/models.py::JobArtifact` demonstrates the shape against a real,
migrated table rather than only a docstring: the demo job's `count` step
(`keel/jobs/demo.py`) writes one `JobArtifact` row per run, setting both
fields from nothing but what `StepContext` already gives every step.
`produced_by_job` is `SET_NULL` on delete precisely so the produced
record outlives the job that made it — see
`keel/jobs/tests/test_models.py::test_provenance_survives_the_job_being_deleted`.
A real ingestion pipeline adds `ProvenanceMixin` to whatever model it
produces rows into and sets the two fields from inside its own job
steps; nothing here needs to change for that to work.

## Audit: making a service audited

Every public, mutating `services.py` callable across the backend must
carry `@keel.core.audit.audited("action.name")` or
`@not_audited(reason=...)` — enforced by a meta-test
(`keel/core/tests/test_service_audit_registry.py`) that walks every
`services.py` in the repo and fails, by name, on any function with
neither. To prove it still bites: stripping `@audited("job.created")` off
`keel.jobs.services.create_job` and running
`test_every_public_mutating_service_is_audited_or_justified` fails with

```
E       assert not ['keel.jobs.services.create_job']
```

restoring the decorator turns the test green again with no other change.

`@audited` records **inline**, immediately after the decorated function
returns — not deferred to `transaction.on_commit()`. `AuditLog` lives in
the same Postgres as everything it describes, so writing the record as
part of the same transaction as the effect is both the safer choice and
the simpler one: if the transaction rolls back, the audit row rolls back
with it, and there is no window where the business effect is durable but
the record of it silently isn't (or vice versa) — verified directly by
`keel/audit/tests/test_recorder.py::test_audit_row_rolls_back_with_the_effect_it_records`,
which deliberately raises inside an open transaction after a call to an
audited service and asserts neither the effect nor the audit row
persisted. `on_commit()` stays the right tool for genuinely external
effects (a Stripe call) — the two are not interchangeable, and audit
writes should never be moved to it.

`@not_audited(reason=...)` is legitimate for: scheduled system jobs with
no actor to record (`purge_old_audit_logs`, `expire_invitations`,
`cleanup_expired_sessions`); an internal helper already covered by the
audited call site that invokes it (`ensure_stripe_customer`, covered by
`create_checkout_session`); and a service whose effect is a
system-triggered side effect of an already-audited call with no actor of
its own (`sync_seat_quantity`, triggered from `on_commit()` by
`accept_invitation`/`remove_member`). It is not legitimate as a way to
skip writing the reason, or to route around the meta-test for a genuine
user-initiated write — every current use is walked and asserted non-blank
by `test_iter_not_audited_reasons_finds_real_production_reasons`.

## Audit ordering and pagination

`GET /orgs/<org_slug>/audit/` orders on `AuditLog.id` (a UUIDv7 primary
key, monotonic by construction — see `keel/core/ids.py`), not
`created_at`. `created_at` is `auto_now_add`, stamped at row-insert time;
two causally-ordered writes across two app-server processes can commit
in either order relative to wall-clock time, and the cursor paginator
filters `created_at__lt=<cursor>` — a row inserted with an
earlier-than-expected timestamp after the client has already paged past
that cursor value would be silently skipped, never returned. `id` needs
no separate tiebreaker (it's already unique), unlike the default
`(-created_at, id)` ordering most other list endpoints use.

Both `listJobs` and `listAuditLogs` are declared through
`keel.core.pagination.paginated` — a decorator that states the
response schema (`Page[X]`) and the ordering once, at the route
declaration, instead of splitting them across a `response=` kwarg, a
bare `paginate(request, queryset)` call in the body, and (whenever the
queryset needs a specific ordering) a third repetition of that ordering
passed to `paginate(..., ordering=...)` — previously easy to get out of
sync, since the third copy is silently overridden if it's ever dropped.
The decorated view returns a plain queryset; `paginated` calls
`paginate()` for it.

## Verifying the invariants above

```bash
cd apps/api
uv run pytest keel/jobs keel/audit keel/core/tests/test_service_audit_registry.py keel/core/tests/test_idempotency.py
uv run python manage.py makemigrations --check --dry-run
uv run lint-imports
uv run python ../../scripts/check_permission_lint.py
```
