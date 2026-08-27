# Phase 16 — Production hardening

**Source of truth:** the "Query hygiene", "Index and migration quality", "Unsafe rendering", "Validation boundary" and "Async boundary" sections of the Notion production-readiness checklist, plus the CI findings Phase 9.C reported.
**Depends on:** Phases 13, 14, 15 merged — this adds query-count tests over endpoints those phases are still changing.
**Size:** Medium.
**Parallelism:** three worktrees. Path ownership below.

---

## Path ownership

| Slice | Owns |
|---|---|
| 16.A | `selectors.py` across every app, new query-count tests, `docs/query-patterns.md` |
| 16.B | Settings (`config/settings/*.py`), `keel/core/checks.py`, startup checks, logging/Sentry scrubbing |
| 16.C | Lint configuration, `apps/web` rendering guardrails, `.eslintrc`/`eslint.config.mjs`, sanitizer wrapper |

16.A touches `selectors.py`; 16.B and 16.C do not. Nobody touches
`services.py` or models.

**No migrations** except an index-only migration in 16.A, if the audit finds
a missing index. Index migrations are additive and are the second
legitimate exception to the baseline invariant.

---

## 16.A — Query hygiene and indexes

There are **no query-count tests in this repository**. `grep` for
`assertNumQueries` or `django_assert_num_queries` across `apps/api` returns
nothing. Every list endpoint is one careless edit away from an N+1 that
nothing catches.

Add query-count assertions to: `/me`, organisation list, members list,
widget list, audit list, file list, and billing overview. Pin the expected
count with a comment explaining what each query is for — a bare
`assertNumQueries(4)` that nobody can justify gets bumped to 5 the first
time it fails, which defeats the point.

Then make them pass: `select_related` / `prefetch_related` belong in
`selectors.py`, which owns query shape. Do not fix an N+1 in a view.

Audit indexes: tenant-scoped foreign keys, common filter and ordering
fields, and composite indexes such as `(organization_id, created_at)` where
a list endpoint orders that way. The cursor paginator's default ordering is
`("-created_at", "id")` — check that is actually backed by an index on every
model it pages.

`docs/query-patterns.md`: how selectors own query shape, how to avoid N+1s,
how to use Django Debug Toolbar locally, and how to add a query-count test
to a new endpoint.

## 16.B — Settings, secrets and logging

Fix what Phase 9.C's gates reported.

`SECRET_KEY` falls back to `"insecure-dev-key-change-me"` in
`config/settings/base.py`. Production must **fail to boot** without a real
one — not warn. Same for any other insecure default that only matters
outside dev. Use `manage.py check` with a custom check (the `keel.core.Exxx`
mechanism already exists in `keel/core/checks.py` — extend it, do not add a
second mechanism), so failure is loud and testable.

Validate `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and CORS origins are set
and are not wildcards in production. Confirm secure cookie settings and HSTS.
Make `check --deploy` pass cleanly under `config.settings.prod`, and flip
Phase 9.C's gate to blocking if it landed non-blocking.

Logging: structured defaults, with redaction of auth headers, cookies,
CSRF and session IDs, OAuth tokens, API keys, Stripe secrets, passwords and
sensitive request fields. `keel/core/logging.py` is the seam. Add a Sentry
`before_send` scrubber (`keel/core/sentry.py` already sets
`send_default_pii: False` — this is the layer below that) and **test it**
with a payload containing each secret type.

Document "no secrets in URLs" and why — URLs reach logs, referrers and
analytics.

## 16.C — Rendering, validation and async boundaries

**Unsafe rendering.** One `dangerouslySetInnerHTML` exists
(`apps/web/components/json-ld.tsx`) and is correctly justified in a comment.
Nothing stops the next one. Add an ESLint rule banning it with an
explicit-justification escape hatch, and a Ruff or Bandit rule for
`mark_safe`, `SafeString` and template `|safe`. If rich user HTML or
Markdown is ever rendered, it goes through one sanitizer wrapper — write the
wrapper and its tests now, or document that no such path exists and the rule
is preventative.

**Validation boundary.** Confirm views validate shape only and delegate
invariants to services. Look for raw `request.data` / raw payload access
bypassing a schema, and for domain rules that leaked into a serializer.
Where the boundary is violated, fix it; where it is fine, say so.

**Async boundary.** Confirm no email send or external HTTP call blocks a
request path, that long work returns **202**, that tasks take IDs rather
than model instances, and that retries and failures are visible. Most of
this should already hold — verify and test rather than assume.

---

## Acceptance — evidence required

**16.A**
- [ ] Query-count tests on all seven named endpoints, each count justified in a comment
- [ ] Every N+1 fixed in `selectors.py`, not in a view
- [ ] Index audit written down; any missing index added in one index-only migration
- [ ] Cursor ordering is index-backed on every paged model
- [ ] `docs/query-patterns.md` written

**16.B**
- [ ] Production **fails to start** on a default `SECRET_KEY`, tested
- [ ] `check --deploy` passes cleanly under `config.settings.prod`; the CI gate is blocking
- [ ] Redaction tested with a payload containing every secret type, in both logs and Sentry `before_send`
- [ ] Wildcard or missing origins fail `manage.py check`, tested

**16.C**
- [ ] Lint blocks `dangerouslySetInnerHTML`, `mark_safe`, `SafeString`, `|safe`, with a documented escape hatch — demonstrated by a deliberate violation failing
- [ ] The existing justified use still passes via the escape hatch
- [ ] Validation-boundary audit written down
- [ ] Async boundary verified: 202 for long work, tasks take IDs, failures visible

## Report back

Per slice: what was already right, what was not, and anything you found that
belongs to a phase that has already merged.
