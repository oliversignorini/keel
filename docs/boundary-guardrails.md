# Rendering, validation and async boundaries

Companion to docs/query-patterns.md — this file covers the other two
legs: unsafe rendering, the validation boundary, and the async boundary.

## Unsafe rendering

**Before this audit:** one `dangerouslySetInnerHTML`
(`apps/web/components/json-ld.tsx`), correctly justified in a comment, but
nothing stopped a second one. Zero `mark_safe`/`SafeString`/`|safe` in
`apps/api` — bandit already catches the first two in `.py` files
(`[tool.bandit]`, `apps/api/pyproject.toml`), but not in templates, and
nothing caught `dangerouslySetInnerHTML` at all.

**Guardrail added:**

- `packages/eslint-config/base.mjs` adds a `no-restricted-syntax` rule
  banning the `dangerouslySetInnerHTML` JSX attribute across every
  workspace that extends this config (today, only `apps/web` — see
  "Lint reach" below). No new dependency (`eslint-plugin-react`'s
  `react/no-danger` was the alternative, but isn't installed).
- `scripts/check_unsafe_rendering.py` greps `apps/api/keel` for
  `mark_safe(`, `SafeString(` and template `|safe`, in both `.py` and
  `.html` files — the one gate that covers templates, and redundant with
  bandit on the Python half by design. Wired into CI's `lint` job
  alongside `check_permission_lint.py`. Same shape as that script:
  test/migration directories exempt, no unit test file of its own (CI
  running it against the real tree, currently clean, is the standing
  proof).

**Escape hatch**, both sides — a same-line comment, not a config
exemption list, so the justification travels with the code:

- TS/TSX: standard `// eslint-disable-next-line no-restricted-syntax --
<reason>`. `json-ld.tsx` now carries one.
- Python/templates: `# unsafe-rendering: <reason>` (or
  `{# unsafe-rendering: <reason> #}` in a template), read by
  `check_unsafe_rendering.py`.

**Proven, not just configured:** `apps/web/lib/lint/unsafe-rendering.test.ts`
lints two in-memory fixtures against the real `base` config — an
unjustified `dangerouslySetInnerHTML` fails, the same line with the
escape-hatch comment passes. `pnpm --filter web lint` also passes clean
over the real tree, confirming `json-ld.tsx`'s existing use survives.

**Sanitizer wrapper:** not written. There is no path in this repo that
renders user- or externally-supplied HTML or Markdown — the only Markdown
is the blog (`apps/web/content-collections.ts`), compiled at **build
time** from `content/blog/*.mdx` files in the repo, not user input.
Documenting that no such path exists and that the rule is preventative:
the two guardrails above are the deliverable; a sanitizer wrapper would
have no caller.

**Lint reach caveat:** only `apps/web` has an ESLint config and a `lint`
script; `packages/ui`, `packages/api-client` and `packages/emails` have
neither, so the new rule only actually executes over `apps/web` today
even though it lives in the shared `base.mjs`. Not a regression — that
was already true of every other rule in `base.mjs` — but worth knowing if
one of those packages ever grows a `dangerouslySetInnerHTML`.

## Validation boundary

**Audited:** every `views.py` across `apps/api/keel` for raw
`request.data`/`request.POST`/`json.loads` of a request body bypassing a
schema, and for domain rules expressed in a serializer rather than a
service.

**What's clean:** every route takes a typed Ninja `Schema` payload — there
is no raw, unvalidated payload access anywhere. The two `request.body`/
`request.GET` reads that do exist
(`keel/billing/views.py:195` Stripe signature verification over raw
bytes; `keel/billing/views.py:100` an ETag cache key from
`request.GET.urlencode()`) are both legitimate — neither is payload
validation being bypassed.

**Violations found, in `keel/organizations/`:**

1. **Fixed** — `OrganizationCreateIn._slug_not_taken`
   (`schemas.py`) ran `Organization.objects.filter(slug=value).exists()`
   inside a Pydantic `field_validator`: an ORM read outside
   `selectors.py` (invariant 1), a domain invariant (uniqueness) enforced
   in the shape layer, and a check-then-act race outside
   `create_organization`'s transaction — two requests could both pass the
   validator for the same slug before either inserted. The validator is
   removed; `slug`'s own `unique=True` DB constraint is now the single
   source of truth — `create_organization` (`views.py`) catches the
   resulting `IntegrityError` and raises `Conflict(code="slug_taken")`.
   Covered by `test_create_organization_rejects_taken_slug_as_conflict`
   (`organizations/tests/test_api_organizations.py`).

2. **Documented, not fixed** — `unique_slug`/`resolve_create_slug`
   (`schemas.py`) still run an ORM read (`Organization.objects.filter(
slug=candidate).exists()`, looped) to auto-generate a free slug when
   none is supplied. This is real domain logic (collision-avoiding slug
   generation), not shape validation, and belongs in
   `selectors.py`/`services.py`, not `schemas.py`. Left in place with
   this note; a follow-up should add a selector for the existence check
   and move slug derivation into `create_organization` itself.

3. **Documented, mitigated** — `_resolve_valid_invitation` (`views.py`)
   duplicates the pending/accepted/revoked/expired check that
   `accept_invitation` (`services.py`) already re-checks inside its own
   `select_for_update` transaction. Not a bug — the service's copy is the
   one that matters for correctness, and the view's copy is also the only
   way `GET /invite/<token>/` (which never calls a service) can reject an
   invalid token. Two sources of the same predicate is still a
   maintenance hazard if they're ever edited independently; not fixed
   here for the same reason as (2) — it belongs in `services.py`, not
   this pass.

4. **Documented, unfixed gap** — the email-match check
   (`invitation.email.lower() != request.auth.email.lower()`,
   `views.py`) is enforced **only** in the view. Unlike (3), nothing
   inside `accept_invitation`'s transaction re-checks it — a future
   caller of `accept_invitation` that isn't this view (an admin action, a
   different API surface) would silently skip the email match. This is
   the one finding here worth prioritising in a follow-up that can touch
   `services.py`.

## Async boundary

**202 semantics:** `createJob` (`keel/jobs/views.py`) is the only 202 in
the API — `response={202: JobOut, 200: JobOut}`, `Status(202, job)` on a
fresh job, the `200` alternative on an idempotent replay. Confirmed by
existing `keel/jobs/tests/` coverage; nothing else in the API does
long-running work synchronously enough to need one.

**Tasks take ids, not model instances:** already enforced for Tier-1
`@task`-shim functions by `keel.core.lint_tasks.check_takes_ids_not_instances`
(`test_meta_task_lint.py`) — but that check only ever walked modules
named `tasks.py` for `Task`-shim instances, so it never covered Tier 2's
raw `@shared_task` functions
(`dispatch_stripe_event`, `sweep_unprocessed_stripe_events`,
`prune_stripe_event_payloads`, `check_credit_balances_task`,
`sweep_stale_uploads`, and `run_job_task`/`sweep_stuck_jobs_task` in
`keel/jobs/runner.py`, which isn't even named `tasks.py`). Added
`discover_shared_tasks`/`check_shared_task_takes_ids_not_instances` to
`keel.core.lint_tasks` (walks every non-test, non-migration module under
`keel`, not just `tasks.py`, since Tier 2 tasks aren't confined to that
filename) and a new meta-test,
`test_meta_shared_task_lint.py::test_every_shared_task_in_the_project_takes_ids_not_instances`,
which now runs this check against every real Tier-2 task in the project —
all of which pass. `process_stripe_event(stripe_event: StripeEvent)` is
correctly excluded: it's a plain function `dispatch_stripe_event` (which
does take an id) calls after its own lookup, not a `@shared_task` itself.

**Retries and failures are visible:**

- Tier-1 shim (`keel/core/tasks.py`): dead-letters after `MAX_RETRIES = 5`
  with jittered backoff, writes a `FailedTask` row **and** reports to
  Sentry (`report_to_sentry`), tested in
  `test_tasks_retry.py::test_dead_lettering_reports_the_exception_to_sentry`.
- **Fixed** — `run_job_task`'s dead-letter path (`keel/jobs/runner.py::
_dead_letter`) wrote a `FailedTask` row but never called
  `report_to_sentry` — an asymmetry with the Tier-1 shim that meant a
  permanently-stuck job dead-lettered silently outside the admin. Now
  calls the same `keel.core.tasks.report_to_sentry` the shim uses.
  Covered by
  `test_runner.py::test_run_job_task_dead_lettering_reports_the_exception_to_sentry`,
  mirroring the shim's own Sentry test.
- `dispatch_stripe_event` sets `StripeEvent.error` and reports to Sentry
  on final failure (`billing/tasks.py`) — already correct.
- `FailedTask` + `FailedTaskAdmin`'s `redrive_selected` action
  (`jobs/admin.py`) gives every dead-lettered task, Tier 1 or 2, a manual
  re-drive path.
- Beat sweepers backstop the "lost message" gaps: `sweep_stuck_jobs_task`
  (a worker killed after the broker's ack, not just before — Celery's
  `CELERY_TASK_ACKS_LATE = True`, confirmed in
  `config/settings/base.py`, only covers the "before ack" case),
  `sweep_unprocessed_stripe_events`, `sweep_stale_uploads`,
  `check_credit_balances_task` (reports drift to Sentry; doesn't repair,
  by design — see its `@not_audited` reason).
- Frontend surfaces job failure directly:
  `apps/web/components/jobs/job-tray.tsx` renders
  `job.error` with `role="alert"` when `job.status === "failed"`.

**Idempotent under re-delivery, not just assumed:** `CELERY_TASK_ALWAYS_EAGER
= True` in test settings means a naive test suite would never exercise
at-least-once delivery — already addressed, not a gap found here:
`keel/jobs/tests/test_idempotent_settlement.py` calls `run_job`,
`_settle_credits`, `cancel_job` and `sweep_stuck_jobs` twice each and
asserts identical ledger/job state; `keel/billing/tests/test_tasks.py::
test_process_stripe_event_is_a_noop_when_already_processed` does the same
for `process_stripe_event`; `keel/files/tests/test_sweep.py` does the
same for `sweep_stale_uploads`. This is the existing, already-followed
convention this repo uses in place of a real broker in tests.

**Blocking calls in the request path:**

- **Real gap, not fixed:** `keel/notifications/adapter.py::
KeelAccountAdapter.send_mail` overrides allauth's synchronous send
  point, so signup email-verification and password-reset **block the
  HTTP request** on a Resend HTTP call with a 10s timeout
  (`config/settings/prod.py`'s `ResendEmailBackend`,
  `keel/notifications/resend_backend.py`). This is allauth's synchronous
  adapter contract, not a bug introduced anywhere in this repo, and
  deferring it would mean either overriding more of allauth's flow than
  this doc's scope covers or accepting weaker signup-flow feedback (no
  immediate "email sent" confirmation) — a real tradeoff, not a drop-in
  fix. Flagged for a deliberate follow-up decision rather than fixed
  here.
- `send_invitation_email`/`send_seat_added_email` are defined but never
  called from production code (only tests) — no request-path email send
  there today.
- The two beat-task email callers (`send_trial_ending_email`,
  `send_payment_failed_email`) already run on a worker — fine as-is.
- `keel/files/services.py::complete_upload` makes a synchronous R2 HTTP
  call (`adapter.head_object`) in the request path — defensible
  (end-to-end verification that the uploaded object actually exists
  before marking the row complete), and named here rather than silently
  accepted.
- Stripe checkout/portal session creation is synchronous by necessity —
  the response _is_ the redirect URL Stripe returns.
- `delete_file` correctly defers the R2 object purge via
  `transaction.on_commit()`, with `sweep_stale_uploads` as the
  backstop for a dispatch that never landed.

**Known gap, out of scope here:** a per-organisation `seq` counter was
added to every SSE event (`keel/jobs/pubsub.py`), documented as letting
a reconnecting client detect a gap and refetch
`GET /orgs/<slug>/jobs/` to resync. The client half was never built —
`apps/web/lib/jobs/types.ts`'s hand-written event types have no `seq`
field, and `use-job-stream.ts` has no gap detection; it only distinguishes
`"connecting"`/`"live"`/`"polling"` connection states. The server pays for
the counter today and nothing reads it. This is a resync-correctness gap
on reconnect, not a request-path blocking or failure-visibility issue, so
it's out of this slice's stated scope ("confirm 202s, task IDs, failure
visibility") — flagged here so it isn't lost, not fixed.
