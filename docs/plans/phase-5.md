# Phase 5 — Async, email, files

**Source of truth:** `keel-prd.md` v1.2 — §4 invariant 5 ("Where does async work run?"), invariant 3 (transaction boundary), the Integration points table, §8 Phase 5.
**Depends on:** Phases 2–4, all merged.
**Size:** Medium. One worktree — the three pieces share the Celery wiring and would collide if split.

---

## Boundary

**In scope:** Celery worker and beat, the retry/dead-letter policy, `FailedTask`, the six scheduled jobs, Resend, six react-email templates, R2 presigned uploads, `<FileUpload>`.

**Out of scope:**

| Thing | Owner |
|---|---|
| `Job` / `JobStep` behaviour, step transitions, SSE, `<JobTray>` | Phase 5.5 |
| `<AppShell>`, command palette, `<DataTable>`, the Widget vertical slice | Phase 6 |
| Marketing routes, MDX | Phase 7 |
| Sentry, PostHog, audit UI, impersonation, rate limiting | Phase 8 |
| `keel-prd.md`, anything under `docs/plans/` | The orchestrator |

**No migrations.** `FailedTask` and `FileUpload` both exist from the Phase 1 baseline. A needed migration means a Phase 1 gap — report it, don't generate one.

---

## Tasks

### 5.1 — Worker and beat

Celery worker and beat running from the **same Docker image** as the API. Add both to `infra/compose.prod.yml`, which Phase 0 left as a stub with a TODO naming this phase.

**Four queues, routed by cost profile, not by domain:** `default`, `email`, `external`, `scheduled`. The PRD is explicit that projects add queues and never collapse these — the separation exists so a hundred queued third-party calls cannot delay a password-reset email. Write that reasoning into the config as a comment; the next person will be tempted.

### 5.2 — The task shim, finalised

`keel/core/tasks.py` exists from Phase 1. Finalise it and hold the line on scope: **Tier 1 only** — single-step work that either succeeds or retries. Do not add chaining, routing, or step semantics. Phase 5.5 uses Celery directly and must not be routed through this.

### 5.3 — Retry, dead-letter, redrive

- Exponential backoff with jitter, 5 attempts.
- Then dead-letter to a `FailedTask` row **plus** a Sentry event. Sentry itself is Phase 8 — call through a seam that is a no-op until then, and say so.
- Re-drivable from Django admin.
- Every task is idempotent by design and **takes IDs, never model instances**. Both of these are lint-enforced acceptance criteria — write the lint rules, and prove each catches a deliberate violation.

### 5.4 — The six scheduled jobs

Stripe plan sync (daily), invitation expiry (hourly), trial-ending notices (daily), dunning check (daily), audit log retention (weekly), expired session cleanup (daily).

Each must be **idempotent when run twice** — that is the acceptance criterion, and the test should run each job twice and assert identical state, the same shape as Phase 4's webhook replay tests.

### 5.5 — Email

Resend integration. Six react-email templates: verification, reset, invitation, trial ending, payment failed, seat added.

Templates are authored in react-email, **rendered to HTML at build**, and sent from Django. That build step is the part that will be fiddly on Windows — if it does not work, say exactly how it fails rather than switching silently to runtime rendering.

Mailpit catches everything in dev. Phase 2 already points `HEADLESS_FRONTEND_URLS` at the Next routes; verification and reset emails must keep working through it.

### 5.6 — Files

R2 presigned direct-upload from the browser: Django issues the signature and records `FileUpload`; the browser uploads straight to R2; the row reaches `complete`.

No R2 credentials exist. Use a MinIO container in `compose.dev.yml` or `moto`, and say which. Uploads must be **organisation-scoped and unreadable across tenants** — that is an acceptance criterion and needs a real cross-tenant test, not an assertion that the key contains the org id.

`<FileUpload>` component: progress, retry, and reconciliation of the `FileUpload` row. It is in the §5 component inventory as of v1.2.

---

## Acceptance — evidence required

- [ ] All six scheduled jobs run and are idempotent when run twice
- [ ] A task raising an exception retries five times with backoff, then dead-letters with a `FailedTask` row and a Sentry event (seam)
- [ ] Every task body is a single call into a service — verified by lint, and the lint demonstrated catching a violation
- [ ] Tasks take IDs, never model instances — verified by lint, demonstrated catching a violation
- [ ] All six emails render and send, and are caught by Mailpit in dev
- [ ] Presigned upload completes from the browser; `FileUpload` reaches `complete`
- [ ] Uploads are scoped to the organisation and cannot be read across tenants
- [ ] A dead-lettered task is re-drivable from Django admin
- [ ] Worker and beat run from the same image as the API, with the four queues routed
- [ ] No migrations were generated

---

## How to work

- Strict TDD on the backend. Tests alongside for `<FileUpload>`.
- Verify, do not assert. Every box needs pasted output.
- Run `ruff check`, `ruff format --check`, `mypy`, `pytest`, and on the web side `eslint`, `prettier`, `tsc`, `vitest` before claiming done. Earlier worktrees shipped unformatted files and a mypy failure by running only some of these.
- Update the Orca worktree comment at each task boundary.
- Do not push, do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; how you stood in for R2 and for Sentry; whether the react-email build step worked on Windows; anything in the PRD that looked wrong from inside the code.
