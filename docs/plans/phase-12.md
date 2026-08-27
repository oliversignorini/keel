# Phase 12 — Railway and Postgres deployment baseline

**Source of truth:** Notion "Keel Phase 12", `infra/railway.json`, `docs/deploy-railway.md`.
**Depends on:** nothing. **Safe to run alongside Phase 10** — it touches `infra/`, settings and docs, not views.
**Size:** Medium.

---

## What already exists

`infra/railway.json` and `docs/deploy-railway.md` are written.
`DATABASE_URL` is already the configuration seam, so provider neutrality is
mostly there. `.env.example` is 7.6KB and thorough.

**What has never happened is a deploy from a clean account.** That is the
work. A deployment guide nobody has followed is a hypothesis.

---

## Boundary

**In scope:** `infra/`, `.env.example`, `docs/deploy-railway.md`,
`docs/maintenance.md`, deployment-related settings in
`apps/api/config/settings/prod.py`, release/migration strategy.

**Out of scope:**

| Thing | Owner |
|---|---|
| Views, serializers, routes | Phase 10 owns those while it runs |
| `check --deploy` findings in application settings | Phase 16 |
| Adding CI gates | Phase 9.C |

**No migrations.**

## Work

**Deploy it, for real, from a clean Railway account.** Backend service,
frontend service, Postgres, Redis, a worker for Celery. Every step you have
to work out that the guide does not tell you is a bug in the guide — fix it
as you go. Note the cost.

**Migration strategy, explicitly.** Do not hide `migrate` in an image build.
Decide: release command, or a one-off job, or manual. Document the choice,
the rollback story, and what happens when a migration fails mid-deploy.

**Provider neutrality, proven.** `DATABASE_URL` must be the only thing that
changes between Railway Postgres and Neon. Verify by pointing a deploy at
each — Railway Postgres is the documented quick path, Neon the advanced
option reserved for Brein. Document connection pooling: Neon's pooled
endpoint and Django's `CONN_MAX_AGE` interact badly if `CONN_MAX_AGE` is
left at the default; say what to set.

**Environment variables.** Reconcile `.env.example` against what a real
deploy actually needed. Every variable: what it does, whether it is
required, what breaks without it. Anything present in `.env.example` that
the deploy did not need should be questioned.

**`docs/maintenance.md`.** Supported Python, Django, Node, Postgres, Redis
versions. Update cadence. A Django upgrade checklist.

**A production checklist** for domains, DNS, TLS, secrets, CORS/CSRF,
allowed hosts, and the first superuser.

## Acceptance — evidence required

- [ ] A deploy was performed from a clean account by following the guide **only**, and every correction is in the diff
- [ ] Both services run; migrations applied by the documented strategy; a superuser was created and logged in
- [ ] Celery worker processes a job in production; result visible in the UI
- [ ] Both Postgres providers verified against the same commit with only `DATABASE_URL` differing
- [ ] Pooling guidance is tested, not repeated from documentation
- [ ] `.env.example` matches reality — no unused variables, none missing
- [ ] `docs/maintenance.md` and the production checklist exist
- [ ] The rollback path was tested at least once

## Report back

What the guide got wrong; the real cost per month; the Railway-vs-Neon
recommendation with reasons; anything that only fails in production.
