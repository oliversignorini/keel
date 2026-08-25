# Phase 5.5 — Long-running jobs and live status

**Source of truth:** `keel-prd.md` v1.2 — §4 invariant 5 (the Tier 1 / Tier 2 boundary), the `Job`/`JobStep` data model entries, §7 the jobs endpoints, §8 Phase 5.5 including its two named deployment footguns, §9 the realtime extension point.
**Depends on:** Phases 3–5, all merged.
**Size:** Medium. One worktree — the models, the runner, the stream and the tray are one mechanism.

---

## Boundary

**In scope:** `Job`/`JobStep` behaviour, the job registry, the resumable base task class, `Idempotency-Key` middleware, per-org concurrency limits, Redis pub/sub, the SSE endpoint on an ASGI service, `useJobStream`, `<JobTray>`, admin redrive for `FailedTask`, and one demo job type.

**Out of scope:**

| Thing | Owner |
|---|---|
| `<AppShell>`, command palette, `<DataTable>`, the Widget vertical slice | Phase 6 — **do not touch `apps/web` beyond `useJobStream` and `<JobTray>`** |
| Marketing routes, blog | Phase 7, merged — leave alone |
| Sentry, PostHog, rate limiting, impersonation | Phase 8 |
| The `init` script | Phase 9 |
| `keel-prd.md`, anything under `docs/plans/` | The orchestrator |

**No migrations.** `Job`, `JobStep` and `FailedTask` all exist from the Phase 1 baseline — v1.2 change #2 put them there precisely so this phase adds no schema. `CreditLedgerEntry.job` already points at `jobs.Job`. If you think you need a migration, that is a Phase 1 gap: report it.

**Do not extend the task shim.** PRD invariant 5 is explicit: `keel/core/tasks.py` covers Tier 1 fire-and-forget work only, and Tier 2 uses Celery directly — chains, per-queue routing, custom base classes, semaphores. The shim's value is portability for work whose entire interface is "run this later"; anything needing step-level commits is a wall to punch through, not a seam. Phase 5 finalised the shim. Leave it alone.

---

## Tasks

### 5.5.1 — The job registry

Each job type declares its steps, its queue, and its credit estimate. This is the one part a project is expected to replace, so keep it small and obvious.

### 5.5.2 — The resumable base task class

Step transitions, per-step commits, resumption from the last completed step, and terminal status resolution **including `partial`**.

`partial` is a real terminal state, not an error: a job that succeeds on 8 of 10 items surfaces its results and releases the unused credit hold.

### 5.5.3 — Idempotency

`Idempotency-Key` middleware on job-creating POSTs, stored 24 hours. Replaying the same key returns the original job and creates **no second row and no second credit hold**. Phase 4's ledger is already in place; wire to it rather than reimplementing.

### 5.5.4 — Per-organisation concurrency

A Redis semaphore. One organisation saturating its limit must not delay another organisation's job — that is the acceptance criterion, and it needs a test with two orgs, not a single-org queue-depth assertion.

### 5.5.5 — SSE, and the two footguns this phase exists to prove

Redis pub/sub publication of step transitions, and an SSE endpoint served **from a dedicated ASGI service** — PRD v1.2 change #7 added it to the deployment topology and `railway.json` for this reason.

**Footgun 1 — SSE holds a connection for its whole life.** Under a sync worker model every connected browser occupies a worker and the pool exhausts far below what request/response load testing suggests. Serve the stream from uvicorn, separately from gunicorn.

**Footgun 2 — reverse proxies buffer by default.** A proxy that buffers `text/event-stream` holds the response until the connection closes. The symptom is not an error; it is a tray that shows nothing for four minutes then everything at once, which reads as "the feature is broken" and is very hard to attribute. Set the headers, configure the proxy, and **assert first-byte latency, not just final content** — the acceptance criterion is first event under one second.

Also document the third, smaller one: HTTP/1.1 caps concurrent connections at six per host per browser, the stream takes one, and on a shared API subdomain that leaves five.

### 5.5.6 — Client

`useJobStream` with automatic fallback to polling on stream loss. `<JobTray>` — persistent, survives navigation **and a full page reload** with jobs still running.

Keep it self-contained. Phase 6 owns `<AppShell>` and will mount the tray; do not build a shell.

### 5.5.7 — Redrive and the demo job

Dead-letter redrive action in Django admin for the `FailedTask` rows Phase 5 introduced. One demo job type with three steps, which `init` deletes alongside the demo resource — so keep it in its own module and note it in the Phase 9 removal list Phase 7 started.

---

## Acceptance — evidence required

- [ ] A job created via POST returns 202 in under 300ms with the work not yet started
- [ ] The same request replayed with the same `Idempotency-Key` returns the original job, and creates no second row and no second credit hold
- [ ] Steps stream to the browser as they transition; **first event reaches the client in under one second** — assert the latency, which is what catches proxy buffering
- [ ] Killing the worker mid-job and restarting resumes at the last completed step rather than from the beginning
- [ ] A job that partially succeeds reaches `partial`, surfaces its results, and releases the unused hold
- [ ] Dropping the SSE connection falls back to polling and the tray stays correct throughout
- [ ] The tray survives a full page reload with jobs still running
- [ ] One organisation saturating its concurrency limit does not delay another organisation's job
- [ ] 50 concurrent SSE connections leave the API serving normal requests at unchanged p95
- [ ] An exhausted task lands in `FailedTask` and is re-drivable from admin
- [ ] The ASGI service is declared in `railway.json` and `infra/compose.prod.yml`
- [ ] No migrations were generated, and the task shim was not extended

---

## How to work

- Strict TDD on the backend. Tests alongside for the tray.
- **Run the thing.** Several acceptance criteria here — first-byte latency, reload survival, polling fallback — are only meaningfully checked by driving a real browser against a real worker. Playwright is available and the dev stack runs with `docker compose -f infra/compose.dev.yml up -d` then `pnpm dev`.
- **Build the email templates first** if you run the API suite: `pnpm --filter @keel/emails build`. A root `conftest.py` will tell you so, but knowing up front saves a cycle.
- Run `ruff check`, `ruff format --check`, `mypy`, `pytest`, plus `eslint`, `prettier`, `tsc`, `vitest` for the client parts.
- Update the Orca worktree comment at each task boundary.
- Do not push, do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; the measured first-event latency and how you measured it; how you proved resumption after a worker kill; anything in the PRD that looked wrong from inside the code.
