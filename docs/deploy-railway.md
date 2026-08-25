# Deploying Keel to Railway

This is a stub. Phase 0 only resolves the one question the PRD calls out as
needing an answer before Phase 5.5 puts embeddings under time pressure:
**does the target Postgres support `pgvector`?** The rest of this doc —
service topology, `railway.json`, the SSE service, env var provisioning —
is written as the phases that need it land.

## pgvector

### Dev image (verified)

`CREATE EXTENSION vector;` succeeds against the dev compose Postgres.

- Image: `pgvector/pgvector:pg17`
- Resolved digest at verification time:
  `pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`
- Server: `PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)`
- Extension version installed: `vector 0.8.6`

```
$ psql -h localhost -p 5433 -U keel -d keel -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
CREATE EXTENSION
 extname | extversion
---------+------------
 vector  | 0.8.6
(1 row)
```

### Target host (Railway) — **not directly verified, no Railway account available in this environment**

Checked via Railway's public documentation and community help station
(no account needed for this much):

- **Railway's standard Postgres plugin — the one you get from "Add
  Database → PostgreSQL" — does not include `pgvector` by default.**
  A Railway moderator's stated guidance on the help station is that
  "enabling pgvector isn't as straightforward" on that default service.
  ([Railway Help Station](https://station.railway.com/questions/enable-pgvector-extension-for-postgre-sql-e861e033))
- Railway instead publishes dedicated templates that ship `pgvector`
  pre-installed, e.g. a "pgvector" template and a "PostgreSQL Extensions"
  template (`EXTENSIONS` env var, pre-compiled extensions including
  `vector`). ([Railway: pgvector template](https://railway.com/deploy/pgvector-latest),
  [Railway: PostgreSQL Extensions template](https://railway.com/deploy/postgresql-extensions))
- One of Railway's official pgvector templates runs the same image family
  we use in dev (`pgvector/pgvector`, e.g. `pgvector/pgvector:0.8.6-pg18`),
  which is reassuring for parity but is a **different service** from the
  default Postgres plugin — provisioning the wrong one is the actual risk.

**Open item — the exact question to answer before Phase 5.5, with an
account:**

> When provisioning Postgres for this project on Railway, deploy the
> `pgvector` template (or the PostgreSQL Extensions template with
> `vector` in `EXTENSIONS`) instead of the default "Add Database →
> PostgreSQL" plugin, and confirm `CREATE EXTENSION vector;` succeeds on
> whatever image tag that template resolves to at deploy time. Record
> the resolved image tag/digest here once done, the same way the dev
> image is recorded above.

Do not provision the default Postgres plugin for this project and
discover the gap during Phase 5.5 — the PRD flags this exact trap.

## Auth cookie domain and Vercel preview deployments

PRD §4 "Auth architecture" / §10 first named risk: the session cookie is
`Domain=.<registrable-domain>` so it is shared between the Next.js app
(`acme.com`, on Vercel) and this API (`api.acme.com`, on Railway). That
constraint has a specific consequence for **Vercel preview deployments**.

- Every PR/branch preview Vercel builds gets a random `*.vercel.app`
  hostname by default. `*.vercel.app` is **not** a subdomain of
  `acme.com`, so a `Domain=.acme.com` cookie set by the API is never sent
  back to a preview deploy — auth silently fails there even though it
  works in production, and it fails in exactly the way `manage.py check`
  (`keel.core.E001`/`E002`, see `apps/api/keel/core/checks.py`) cannot
  catch, because the *server-side* config is correct; the mismatch is
  between the server's configured domain and whichever preview URL Vercel
  handed out for that request.
- **Resolution: a wildcard preview domain.** Configure Vercel to serve
  previews at `*.preview.acme.com` instead of `*.vercel.app` — this
  **requires a Vercel Pro plan** (wildcard domains are not available on
  the Hobby tier). Pair it with a staging API at `api.preview.acme.com`,
  sharing `Domain=.acme.com` with the app the same way production does
  (or `Domain=.preview.acme.com` if staging is meant to be cookie-isolated
  from production — pick one and keep the API's `KEEL_APP_DOMAIN` /
  `DJANGO_SESSION_COOKIE_DOMAIN` consistent with whichever choice is
  made).
- `init` is expected to prompt for and configure both the production and
  preview domains up front (PRD §4), since retrofitting a domain choice
  after cookies are already in use in production is disruptive.
- Without Vercel Pro (or before the wildcard domain is set up), expect
  preview deployments to be unauthenticated-only — fine for reviewing UI,
  not for testing the auth flow itself. Test auth against a real
  `api.<domain>` + `<domain>` pair (or `localhost` in dev, where the
  cookie is host-only and this constraint doesn't apply — see
  `apps/api/.env.example`'s `KEEL_APP_DOMAIN` comment).

## Everything else

Not written yet. `railway.json`, service topology (api / worker / beat /
the dedicated SSE uvicorn service per the Appendix note on
`text/event-stream` buffering), and env var provisioning arrive with the
phases that need them.
