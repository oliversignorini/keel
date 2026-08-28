# Deploying Keel to Railway

Status as of Phase 12 (`docs/plans/phase-12.md`): every config, script and
doc a deploy needs is written and, where it doesn't require a live Railway
account, verified locally against a real Postgres/Redis and a real Docker
build (see "What was verified without a Railway account" below). **The
actual first deploy from a clean Railway account has not happened** — no
Railway account was available in this environment, and provisioning one is
listed as a blocked step. Everything in this doc that depends on that is
marked so explicitly; treat those sections as the best-effort account of
what should happen, not as evidence that it does.

## What was verified without a Railway account

Real, reproducible evidence — not documentation-reading — for the parts
that don't require Railway itself:

- `apps/api/Dockerfile` builds successfully (`docker build -f
apps/api/Dockerfile apps/api`), including the `collectstatic` step run
  at build time.
- The built image, run against `infra/compose.dev.yml`'s real Postgres and
  Redis containers:
  - `python manage.py migrate --no-input` applies cleanly.
  - `gunicorn config.wsgi:application` (the `api` service's exact
    `startCommand`) serves `/healthz/` → `200 {"status": "ok"}`, the Django
    admin login page → `200`, and a `/static/...` asset → `200` (WhiteNoise
    serving the `collectstatic` output — see "Static files" below).
  - `uvicorn config.asgi_stream:application` (the `stream` service's exact
    `startCommand`) serves its own `/healthz/` → `200`.
  - `celery -A config worker -Q default,email,external,scheduled` (the
    `worker` service's exact `startCommand`) connects to Redis and reports
    all ten registered tasks.
- `uv lock` resolves cleanly with `gunicorn` and `whitenoise` added as
  dependencies (`apps/api/pyproject.toml`, `apps/api/uv.lock`).
- `apps/api/.dockerignore` (new) keeps a local `.env` and dev caches out
  of the build context — confirmed the build still succeeds with it in
  place.

None of this proves Railway's own build/deploy/proxy layer behaves the
same way — see the open questions under "Service topology" below, which
are exactly the parts only a real account can answer.

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
  catch, because the _server-side_ config is correct; the mismatch is
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

## Service topology and `railway.json` (Phase 5.5, Dockerfile added Phase 12)

`infra/railway.json` declares four services, all built from the same
`apps/api` image (`apps/api/Dockerfile`, added in Phase 12 — a multi-stage
`uv`-based build, non-root runtime user, `collectstatic` run at build time.
Not needed by `infra/compose.prod.yml`'s TODO comment any more; that
comment is now stale and should be removed the next time someone touches
that file, but this phase does not own it):

| Service  | Command                                                       | Why it's separate                                                                                                                                                                                                                                                        |
| -------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `api`    | `gunicorn config.wsgi:application`                            | Ordinary request/response traffic, sync workers                                                                                                                                                                                                                          |
| `stream` | `uvicorn config.asgi_stream:application`                      | SSE only — `keel/jobs/sse.py`, reachable at `.../jobs/stream/`. Never gunicorn: a held-open SSE connection occupies a sync worker for its entire life, exhausting the pool at a user count far below what request/response load testing suggests (PRD §5.5.5, footgun 1) |
| `worker` | `celery -A config worker -Q default,email,external,scheduled` | Tier 1 shim tasks and Tier 2 job runner (`keel/jobs/runner.py`)                                                                                                                                                                                                          |
| `beat`   | `celery -A config beat`                                       | The six scheduled jobs (PRD §5)                                                                                                                                                                                                                                          |

**Not directly verified against a live Railway account or the Railway
CLI.** `infra/railway.json`'s shape (`services` keyed by name, each with
`build`/`deploy`) matches Railway's documented config-as-code schema
(`docs.railway.com/config-as-code/reference`, checked 2026-08), and each
service's exact `startCommand` was run locally against the built image
(see "What was verified without a Railway account" above) — but neither
of those proves Railway's own build pipeline, edge proxy, or per-service
networking behaves the same way. Before the first real deploy, confirm
against `railway up`/the dashboard that:

- Railway actually reads a multi-service `railway.json` this shape
  (vs. requiring one config file per service, set via each service's
  "Config File Path")
- `$PORT` is available to `stream` as its own distinct port the way it
  is to `api` — Railway assigns one `$PORT` per _service_, not per
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
on 8000). `KEEL_API_STREAM_INTERNAL_URL` (`.env.example`; server-only
since docs/adr/0002-auth-bff-shape.md — the browser no longer talks to
`stream` directly, the Next.js BFF proxy does) points the web app's
server process at whichever port `stream` is actually running on.

Env var provisioning beyond what's already in `.env.example` arrives
with Phase 9 (`init`).

## Static files

The Django admin (and Ninja's own `/api/v1/docs` schema UI) need their CSS/JS
served somehow in production; `DEBUG=True` serves `STATIC_ROOT` directly
in dev, which stops working the moment `prod.py` sets `DEBUG = False`.
`apps/api/config/settings/prod.py` adds `whitenoise.middleware.
WhiteNoiseMiddleware` (inserted right after `SecurityMiddleware`, matching
WhiteNoise's own documented placement) and sets `STORAGES["staticfiles"]`
to `whitenoise.storage.CompressedManifestStaticFilesStorage`.
`apps/api/Dockerfile` runs `collectstatic` at build time, so the compiled,
hashed, gzip/brotli-compressed assets are already in the image before the
container starts — no static-file step at deploy time, no separate CDN or
object-storage bucket for what is, today, only framework-provided pages.
Verified locally: see "What was verified without a Railway account" above.

This is not a general-purpose asset pipeline — Next.js on Vercel serves
the actual application's static assets, entirely separately. WhiteNoise
here covers only what Django itself renders.

## Migration strategy

**Decision: `preDeployCommand`, not `migrate` hidden in the image build,
not a manual step.**

`infra/railway.json`'s `api` service sets:

```json
"preDeployCommand": ["python manage.py migrate --no-input"]
```

Railway runs a service's `preDeployCommand` after a successful build and
before that deploy's `startCommand`, in its own container with the
deploy's environment variables and private-network access, but **no
persistent filesystem and no mounted volumes** — irrelevant here since
`migrate` only needs `DATABASE_URL`. If it exits non-zero, the deploy is
aborted and the previous deploy keeps serving traffic; it is not retried
automatically. (`docs.railway.com/deployments/pre-deploy-command`,
checked 2026-08 — Railway's own docs don't say whether a service with
zero replicas or a service that's never been deployed before runs it
differently; that is a real-account open item, listed below.)

**Only the `api` service declares it — `stream`, `worker` and `beat` do
not.** All four services build from the same image and would each run
their own copy of `preDeployCommand` on every deploy if it were repeated;
since Railway deploys are triggered per-service (a push that changes
`apps/api/**` redeploys all four), that would mean up to four concurrent
`migrate` invocations racing on every deploy. Django wraps each migration
in its own transaction on Postgres, so a second concurrent `migrate` run
mid-migration blocks on a lock rather than corrupting anything — but
"blocks and eventually times out or serializes" is not a property to rely
on when "runs exactly once" is available for free by picking one service
to own it.

**Why not hidden in the image build (`docker build` running `migrate`):**
a migration needs a live database connection and the _target_ environment's
credentials, neither of which exist at build time — and coupling the two
means a build that succeeds says nothing about whether the migration
against production data will.

**Why not manual:** a manual step is a step someone forgets, and it
reintroduces exactly the race this phase is trying to close — a service
starting against a schema its own code doesn't expect yet.

**Rollback story.** Two failure shapes, handled differently:

- **The migration itself fails (bad SQL, a broken constraint against real
  data).** `preDeployCommand` failing aborts the deploy — the previous
  `api`/`stream`/`worker`/`beat` deploys keep running against the
  unmigrated (and therefore still-consistent) schema. No code from the
  failed deploy ever goes live. Fix the migration, redeploy.
- **The migration succeeds but the new application code is broken.**
  This is the shape Django migrations are meant to survive: every
  migration in this codebase must be backward-compatible with the
  previous release's code for at least one deploy (add-nullable-column,
  not rename-and-drop-in-one-step — the standard Django "expand/contract"
  pattern). Rolling back the _code_ (Railway's dashboard has a one-click
  "redeploy a previous build") while leaving the _schema_ migrated forward
  is the recovery path — rolling the schema back too is a last resort,
  since a `migrate <app> <previous_number>` against data written by the
  rolled-forward schema can itself be destructive (dropped columns lose
  data on reverse). **Not tested against a real failing migration in this
  phase** — no Railway account to deploy a deliberately-broken migration
  against — see the human checklist below.

## Environment variables — reconciled

`.env.example` was read end-to-end against every `env(...)` /
`env.bool(...)` / `env.int(...)` / `env.list(...)` call in
`apps/api/config/settings/`. Every variable Django reads has an entry;
nothing in `.env.example` was found unused. New in Phase 12:

| Variable                                | Required in prod?                                                                                      | What breaks without it                                                                                                                                                                           |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `DJANGO_DB_CONN_MAX_AGE`                | No — defaults to `0` (no persistent connections), which is the safe default for Neon's pooled endpoint | On Railway Postgres (no pooler in front of it), leaving this at `0` costs a fresh TCP+TLS handshake per request; see "Pooling" below                                                             |
| `DJANGO_DB_DISABLE_SERVER_SIDE_CURSORS` | No — defaults to `False`                                                                               | On Neon's pooled endpoint, leaving this `False` risks a server-side cursor opened in one pooled transaction and used in another that got a different underlying connection — see "Pooling" below |

**Full env-var-to-provider reconciliation (which variables a real Railway
deploy needed vs. `.env.example`'s existing set) is a blocked step** — it
needs the actual deploy this phase could not perform. What's true from
reading the settings code alone:

- `DATABASE_URL`, `REDIS_URL` — not set by hand on Railway. Railway
  injects them automatically when a Postgres/Redis plugin is attached to
  the project and the service references it via `${{Postgres.DATABASE_URL}}`
  / `${{Redis.REDIS_URL}}` (Railway's variable-reference syntax, set in
  the dashboard's Variables tab — this is not expressible in
  `railway.json`; see the human checklist).
- `PORT` — set automatically by Railway per service; `infra/railway.json`'s
  `startCommand`s already read `$PORT` rather than hardcoding 8000/8001.
- `RAILWAY_GIT_COMMIT_SHA` — set automatically by Railway; already read by
  `apps/api/config/settings/base.py` (`SENTRY_RELEASE`).
- Every other variable in `.env.example` is either read directly by
  `base.py`/`prod.py` (verified by the grep above) or is a
  `NEXT_PUBLIC_*` Next.js/Vercel variable, out of this phase's scope
  (Vercel project settings, not `infra/`).

## Postgres provider neutrality — Railway vs. Neon

`DATABASE_URL` is already the only thing `apps/api/config/settings/base.py`
reads to configure the database (`env.db("DATABASE_URL", ...)`, parsed by
`django-environ`) — no code path branches on which provider issued the
URL. That was true before this phase; what this phase adds is the pooling
behavior that makes it _safely_ true rather than just _nominally_ true.

**Railway Postgres — the documented quick path.** Provision via "Add
Database → PostgreSQL" (or the `pgvector` template if `pgvector` is
needed — see the pgvector section above). No connection pooler sits in
front of it by default, so:

```
DJANGO_DB_CONN_MAX_AGE=60
DJANGO_DB_DISABLE_SERVER_SIDE_CURSORS=false
```

Sixty seconds, not "forever" (`None`/`-1`): Railway's default Postgres
plan connection limit is finite and shared across `api` + `worker` +
`beat` (`stream` doesn't touch the database directly), and a persistent
connection per gunicorn sync worker adds up quickly under
`--workers`/`--threads` scaling. Sixty seconds amortizes the handshake
cost without holding connections indefinitely.

**Neon — the advanced option reserved for Brein.** Neon's dashboard hands
out a **pooled** connection string by default (hostname contains
`-pooler`), which is PgBouncer in transaction-pooling mode — the
underlying Postgres connection is returned to Neon's own pool at the end
of every transaction, not held for the life of the client connection.
Combined with Django's own `CONN_MAX_AGE` (which pools at the
_application_ layer, reusing one psycopg connection across requests) this
interacts badly in two ways, both documented by Neon
(`neon.com/docs/connect/connection-pooling`, checked 2026-08):

1. A Django-side persistent connection on top of a transaction-mode pooler
   pools nothing extra — it just holds a slot in Neon's own limited
   pooler for no benefit, working against the thing the pooler exists to
   provide.
2. Transaction-mode pooling does not preserve session state (`SET`,
   `LISTEN`/`NOTIFY`, and SQL-level server-side cursors) across pooled
   transaction boundaries — a cursor opened in one transaction can be
   handed a _different_ underlying connection on its next fetch.

So, for Neon:

```
DJANGO_DB_CONN_MAX_AGE=0
DJANGO_DB_DISABLE_SERVER_SIDE_CURSORS=true
```

Both are this repo's defaults already (`prod.py`'s `env.int`/`env.bool`
calls) — Neon is safe with no env vars set at all; Railway Postgres is the
one that needs the two above set explicitly to get persistent connections.
That asymmetry is intentional: the safe-by-default choice should be the
one that can't silently corrupt a cursor.

**Not verified against either live provider** — both bullet points above
are read from `django-environ`'s and Neon's own documentation, not from a
deploy pointed at each. Doing that (two deploys of the same commit, one
per `DATABASE_URL`, diffing nothing else) is a blocked step — see the
human checklist.

## Production checklist

Before the first real deploy goes live for real users:

- [ ] **Domains.** `api.<domain>` (Railway custom domain, or the
      Railway-issued `*.up.railway.app` for a first smoke test) and
      `<domain>` / `app.<domain>` (Vercel). See "Auth cookie domain" above for
      why the registrable domain must match between them.
- [ ] **DNS.** `CNAME`/`A` records per the domain provider's instructions
      for both Railway and Vercel custom domains. Both platforms issue their
      own TLS certs once DNS is verified — no manual cert step on either.
- [ ] **TLS.** `DJANGO_SECURE_SSL_REDIRECT=true` (this repo's `prod.py`
      default). `prod.py` also sets `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO",
"https")` so Django trusts Railway's edge-forwarded scheme — confirmed
      against Railway's own docs that its edge sets this header
      (`docs.railway.com/networking/edge-networking`, checked 2026-08), not
      yet confirmed against a real deploy inspecting the header Railway
      actually sends (see the human checklist).
- [ ] **Secrets.** `DJANGO_SECRET_KEY`, `KEEL_ENCRYPTION_KEY` — both must
      be freshly generated per environment, never the `.env.example`
      placeholder values, and never reused between staging and production.
      `DJANGO_SECRET_KEY` failing this is now a hard boot failure, not
      just `security.W009` (`keel.core.checks.check_secret_key_not_default`,
      phase 16.B). `KEEL_ENCRYPTION_KEY` rotates safely (ddia#27,
      `apps/api/keel/core/crypto.py`): set it to `<new-key>,<old-key>`
      (comma-separated, newest first — every configured key can decrypt,
      only the first encrypts), then run
      `python manage.py rotate_connection_tokens` to move existing
      `Connection` rows onto the new key before dropping the old one from
      the env var.
- [ ] **CORS/CSRF.** `DJANGO_CORS_ALLOWED_ORIGINS` and
      `DJANGO_CSRF_TRUSTED_ORIGINS` set to the real production origins
      (`https://app.<domain>`, `https://<domain>`) — the `.env.example`
      defaults are `lvh.me` dev origins and must not ship to prod.
- [ ] **Allowed hosts.** `DJANGO_ALLOWED_HOSTS` set to `api.<domain>` (and
      Railway's own `*.up.railway.app` host if that's kept reachable as a
      fallback) — the `.env.example` default is `lvh.me,.lvh.me,localhost,
127.0.0.1` and must not ship to prod.
- [ ] **First superuser.** `python manage.py createsuperuser` — run once,
      against the production database, via `railway run` (executes against
      the deployed environment's variables without a separate SSH step) or a
      one-off Railway "Run Command" from the dashboard. Not `preDeployCommand`
      — that runs on every deploy and `createsuperuser` isn't idempotent.
- [ ] **`manage.py check --deploy` clean** (or every warning explicitly
      accepted) against `config.settings.prod` with real production env vars
      — `docs/plans/phase-9.md` 9.C wires this into CI against placeholder
      vars; run it again by hand against the real ones before the first
      deploy, since a placeholder passing doesn't prove a real secret does.
- [ ] **Sentry, PostHog, Stripe, Resend, Google OAuth** credentials set
      (`SENTRY_DSN`, `POSTHOG_PROJECT_API_KEY`, `STRIPE_SECRET_KEY` +
      `STRIPE_WEBHOOK_SECRET`, `RESEND_API_KEY`, `GOOGLE_OAUTH_CLIENT_ID` +
      `GOOGLE_OAUTH_CLIENT_SECRET`) — each is a documented no-op when blank
      (see `base.py`'s comments on each), so a blank one fails silently
      rather than loudly; verify each is actually set, don't rely on an error
      to notice one was missed.

Every unchecked box above that needs a live Railway/Vercel account is
also on the human checklist at the bottom of this doc.

## Cost estimate

Railway's pricing (`docs.railway.com/pricing/plans`, checked 2026-08) is
usage-based on top of a plan minimum: **Hobby, $5/month minimum**, billed
at `$10/GB-RAM/month`, `$20/vCPU/month`, `$0.05/GB`network egress,`$0.15/GB/month` volume storage — the plan fee is credited against usage,
not charged on top of it.

Four services (`api`, `stream`, `worker`, `beat`) at a conservative
low-traffic sizing (0.5 vCPU / 512MB each, Railway's own low end) plus a
small Postgres volume and Redis:

| Resource                                                      | Sizing                                          | Monthly cost                                                                                     |
| ------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `api` + `stream` + `worker` + `beat` compute                  | 4 × (0.5 vCPU, 512MB RAM), running continuously | 4 × (0.5×$20 + 0.5×$10) = **$60**                                                                |
| Postgres volume                                               | 1GB to start                                    | **$0.15**                                                                                        |
| Redis (no persistent volume needed for cache+broker use here) | —                                               | **~$0**                                                                                          |
| Network egress                                                | Low-traffic estimate, 5GB/month                 | **$0.25**                                                                                        |
| **Total**                                                     |                                                 | **≈ $60–65/month**, Pro plan ($20 minimum) since Hobby's $5 credit is exhausted well before this |

This is a **written estimate from Railway's published per-unit rates, not
a real bill** — actual usage-based cost depends on real traffic and was
not measured, since no deploy ran. The dominant cost by far is running
four always-on compute services continuously; `worker` and `beat` in
particular are idle most of the time for a low-traffic project and are
the first place to look if the real bill runs high (Railway supports
scale-to-zero for some service types — not evaluated here, since Celery
workers and beat schedulers are not good scale-to-zero candidates: a
worker that's asleep when a job is dispatched adds latency, and beat
sleeping means missed scheduled runs).

Compare: Neon's free tier covers Postgres entirely for a low-traffic
project (its paid tiers start around $19/month at meaningfully higher
usage) — since `DATABASE_URL` is the only thing that changes, pairing
Railway compute with Neon Postgres instead of Railway's own Postgres is a
real way to cut the estimate above, at the cost of the pooling caveats
documented under "Postgres provider neutrality."

## Vercel (frontend)

Out of this phase's file-ownership (`apps/web` and Vercel project
settings belong to whichever phase actually deploys the frontend — see
`docs/review-2026-08.md` on the BFF gap this repo currently has), but
part of "deploy it, for real" as the plan states it. What's needed,
documented here since `docs/deploy-railway.md` is where the cross-service
auth-cookie constraint already lives:

1. Import the repo into a new Vercel project, root directory
   `apps/web`, framework preset Next.js (auto-detected).
2. Set every `NEXT_PUBLIC_*` variable from `.env.example`'s "Web" section
   to the real production values, plus the two server-only ones Vercel
   never exposes to the browser bundle — `KEEL_API_INTERNAL_URL` and
   `KEEL_API_STREAM_INTERNAL_URL` — pointing at the deployed Railway
   `api` and `stream` services' real hostnames. Since
   docs/adr/0002-auth-bff-shape.md, those two are what the BFF proxy
   itself dials; nothing in the browser needs Django's address anymore.
3. Configure the custom domain(s) and, if preview-deployment auth testing
   matters, the wildcard preview domain described above (**Vercel Pro
   required**).
4. Confirm `KEEL_APP_DOMAIN` / `DJANGO_SESSION_COOKIE_DOMAIN` on the
   Railway side match the real registrable domain Vercel is serving from
   — this is the single most likely thing to be wrong on a first deploy,
   per the "Auth cookie domain" section above.

**Not performed** — Vercel account provisioning is a blocked step, listed
below.

## Human checklist — steps that need a real account or paid resources

Everything below requires a live Railway account (or Vercel/Neon account)
and could not be attempted in this environment. Each is otherwise fully
prepared by the config/docs/scripts in this phase's diff.

1. **Create a Railway account and project**, connect this repo (or a fork
   of it) via GitHub.
2. **Provision Postgres.** Either Railway's own "Add Database →
   PostgreSQL" (or the `pgvector` template, if `pgvector` is needed — see
   the pgvector section above) or a Neon project + database, per the
   provider-neutrality section above.
3. **Provision Redis** ("Add Database → Redis").
4. **Create the four services** (`api`, `stream`, `worker`, `beat`) from
   this repo, each pointed at `infra/railway.json` (confirm Railway
   actually reads one multi-service file this shape — see "Service
   topology" above's open item).
5. **Set environment variables** in each service's Variables tab: the
   full `.env.example` set with real values, plus
   `${{Postgres.DATABASE_URL}}` / `${{Redis.REDIS_URL}}` variable
   references (Railway's own reference syntax — not expressible in
   `railway.json`).
6. **Trigger the first deploy** and confirm: build succeeds,
   `preDeployCommand` (`migrate`) succeeds, all four services report
   healthy, `/healthz/` responds on `api` and `stream`.
7. **Create the first superuser** via `railway run python manage.py
createsuperuser` (or the dashboard's one-off Run Command) and log in
   to `/admin/`.
8. **Dispatch a real Celery job** (any of the six scheduled tasks, or the
   demo job `keel.jobs.demo` registers) and confirm the `worker` service
   processes it and the result is visible wherever the app surfaces job
   results.
9. **Confirm SSE isn't buffered** by Railway's edge proxy in front of
   `stream` — open a real SSE connection through the public URL and
   confirm events arrive incrementally, not batched (the specific risk
   "Service topology" above calls out).
10. **Deploy the same commit a second time pointed at Neon instead of
    Railway Postgres**, changing only `DATABASE_URL` (and the two pooling
    env vars per "Postgres provider neutrality" above), and confirm it
    behaves identically — this is the acceptance criterion "both
    providers verified against the same commit."
11. **Deliberately break a migration** (e.g. a bad column rename) on a
    disposable environment, trigger a deploy, and confirm the rollback
    story above actually holds — the previous deploy keeps serving, the
    failure is visible in Railway's deploy log, and the documented
    recovery steps work.
12. **Create a Vercel account/project** for the frontend, per the "Vercel
    (frontend)" section above, including the Pro-plan wildcard preview
    domain if preview-deployment auth testing is wanted.
13. **Confirm `SECURE_PROXY_SSL_HEADER`'s header actually arrives.**
    `prod.py` now trusts `X-Forwarded-Proto` from Railway's edge
    (confirmed via Railway's docs, not via a real request) — inspect an
    actual request's headers on a live deploy to make sure the redirect
    doesn't loop.
14. **Record the real monthly bill** after a week or two of running, and
    compare it against the written estimate in "Cost estimate" above —
    replace the estimate with the measured number once one exists.
