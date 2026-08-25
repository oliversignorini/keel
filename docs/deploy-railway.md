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

## Service topology and `railway.json` (Phase 5.5)

`infra/railway.json` declares four services, all built from the same
`apps/api` image (`apps/api/Dockerfile` — not written yet; see the
Phase 9 TODO in `infra/compose.prod.yml`, which the `api`/`stream`
services here are written against on the same terms):

| Service | Command | Why it's separate |
|---|---|---|
| `api` | `gunicorn config.wsgi:application` | Ordinary request/response traffic, sync workers |
| `stream` | `uvicorn config.asgi_stream:application` | SSE only — `keel/jobs/sse.py`, reachable at `.../jobs/stream/`. Never gunicorn: a held-open SSE connection occupies a sync worker for its entire life, exhausting the pool at a user count far below what request/response load testing suggests (PRD §5.5.5, footgun 1) |
| `worker` | `celery -A config worker -Q default,email,external,scheduled` | Tier 1 shim tasks and Tier 2 job runner (`keel/jobs/runner.py`) |
| `beat` | `celery -A config beat` | The six scheduled jobs (PRD §5) |

**Not directly verified against a live Railway account or the Railway
CLI** — written from Railway's documented multi-service `railway.json`
schema (`services` keyed by name, each with `build`/`deploy`), the same
epistemic status as the pgvector section above. Before the first real
deploy, confirm against `railway up`/the dashboard that:

- Railway actually reads a multi-service `railway.json` this shape
  (vs. requiring one config file per service, set via each service's
  "Config File Path")
- `$PORT` is available to `stream` as its own distinct port the way it
  is to `api` — Railway assigns one `$PORT` per *service*, not per
  container, so this should hold, but is worth confirming once
  `stream` is a real deployed service rather than a local `uvicorn`
  process
- the proxy in front of `stream`'s public domain does not buffer
  `text/event-stream` by default. `keel/jobs/sse.py` sets
  `X-Accel-Buffering: no` (the nginx-family signal) and flushes a
  leading `: connected` comment before ever touching Redis; Railway's
  own edge proxy has not been checked against either of those. If it
  does buffer, the symptom is exactly the one PRD §5.5.5 warns about:
  not an error, a tray that shows nothing for minutes then everything
  at once.
- `api` and `stream` are given **different public hostnames or paths**
  so `stream`'s healthcheck and TLS termination don't collide with
  `api`'s — the PRD's own diagram shows one hostname with path routing
  (`api.acme.com/…/stream`), which is a reverse-proxy rule Railway's
  edge would need to be configured with, not something `railway.json`
  alone expresses.

Dev runs `stream` as a second local process, not via Railway or
Docker Compose: `pnpm --filter api dev:stream` (wraps `uv run uvicorn
config.asgi_stream:application --port 8001 --reload`), alongside the
usual `pnpm --filter api dev` (gunicorn's dev equivalent, `runserver`,
on 8000). `NEXT_PUBLIC_API_STREAM_URL` (`.env.example`) points the web
app at whichever port `stream` is actually running on.

Env var provisioning beyond what's already in `.env.example` arrives
with Phase 9 (`init`).
