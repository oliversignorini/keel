# Deploying Keel to Railway

Status: **deployed, for real.** Django and Next.js both run on Railway,
serving over HTTPS, against Railway-managed Postgres and Redis, with
migrations applied by `preDeployCommand` and the Next.js BFF reaching
Django over the private network. Everything below is written from that
deploy. Where something has *not* been exercised it says so in those
words — the previous version of this document was written from Railway's
documentation without an account, and most of what it asserted turned out
to be wrong in ways that each failed a deploy.

Verified live at the time of writing:

| Check                                                             | Result                                                       |
| ----------------------------------------------------------------- | ------------------------------------------------------------ |
| `apps/api/Dockerfile` builds on Railway                           | 115MB image, `collectstatic` 141 files / 421 post-processed  |
| `preDeployCommand` migrations                                     | every app applied cleanly, idempotent on redeploy            |
| `/healthz/`                                                       | `200 {"status": "ok"}`                                       |
| Django admin, `/api/v1/docs`, `/_allauth/browser/v1/config`       | `200`                                                        |
| WhiteNoise hashed asset (`/static/admin/css/base.<hash>.css`)     | `200`                                                        |
| Next.js app on Railway                                            | `200`, standalone server, non-root                           |
| BFF to Django over `api.railway.internal`                         | `200` JSON                                                   |
| `pgvector` on Railway's managed Postgres                          | `CREATE EXTENSION vector` succeeds, `vector 0.8.6`           |
| HTTPS redirect on, healthcheck still passing                      | both, via `SECURE_REDIRECT_EXEMPT`                           |

Not yet exercised: `worker`, `beat` and `stream` as deployed services
(see "Service count" below), Celery processing a real job, SSE through
Railway's edge, a deliberately-broken migration, and Neon as the
database.

## Configuration: `.railway/railway.ts`, not `railway.json`

**Railway's Config as Code (`railway.json` / `railway.toml`) is
deprecated. New services cannot opt into it at all, and existing files
stop being read on 2026-12-01.** The replacement is Infrastructure as
Code: one `.railway/railway.ts` per project, applied with the CLI.

```bash
railway login && railway link
railway config plan          # preview
railway config apply         # apply after confirmation
```

The repo previously carried `infra/railway.json` with a top-level
`{"services": {...}}` map. That shape was never a schema Railway read —
Config as Code was per-*service*, with `build`/`deploy` at the top level
and no way to describe four services at once. The four services it
described could not have been provisioned from it. It has been deleted.

Things worth knowing about the IaC DSL, all found by using it:

- `restartPolicyType` / `restartPolicyMaxRetries` are only read under
  `deploy:`. As top-level service keys they are silently dropped — the
  plan showed `restartPolicyMaxRetries 5 -> null`.
- `github(repo)` defaults the branch to `main` and does **not** read the
  repository's actual default branch. This repo's is `master`. Pass
  `branch` explicitly.
- `railway config apply` **exits 0 when the apply fails** and prints
  nothing about it. The failure is only visible with `--json`, under
  `applyResult.status` / `applyResult.diagnostics`. Anything running this
  in CI must check that, not the exit code.
- An apply is atomic: if any one resource exceeds a plan limit, the whole
  change set fails and *nothing* is created. Creating services one at a
  time gets further on a constrained plan.
- A failed apply can still leave service rows behind that exist at
  project level with no environment instance. `railway service delete`
  cannot see them ("not found in environment"), IaC does not track them
  (`0 to destroy`), and they still count against the plan's service
  limit. Deleting them needs the dashboard, because the API path requires
  2FA that an API token cannot satisfy.

## Service count — the topology does not fit on Hobby

Keel is seven Railway resources: `api`, `stream`, `worker`, `beat`,
`web`, Postgres, Redis.

**Hobby caps a project at 5 services.** Not the Trial — Hobby. Confirmed
against the live plan limits (`project.services: 5`). The error Railway
returns says "Free plan resource provision limit exceeded" regardless of
which plan the account is actually on, which makes it look like a Trial
problem when it is not. Pro is required for the full topology.

The deploy this document describes ran `api`, `web`, Postgres and Redis —
four of the seven — which is what fits.

## Start commands take a literal port

**Railway execs a service's start command without a shell.** `$PORT`
arrives at gunicorn as five literal characters and it exits:

```
Error: '$PORT' is not a valid port number.
```

Wrapping it as `sh -c "... $PORT"` does **not** help; the wrapper is not
given a shell either. Every `startCommand` in the old `infra/railway.json`
used `$PORT`, so all four would have crashlooped on first boot.

`.railway/railway.ts` pins the port literally instead, and sets `PORT` to
match so Railway's own port detection agrees:

```ts
const API_PORT = "8080";
start: `gunicorn config.wsgi:application --bind 0.0.0.0:${API_PORT}`,
env: { ...appEnv, PORT: API_PORT },
```

A fixed port is needed anyway: the Next.js BFF dials
`api.railway.internal` and has to know which port to use.

## `ALLOWED_HOSTS` needs three hosts, for three different callers

Setting it to the public hostname alone — what the previous version of
this document told you to do — fails the deploy.

```
DJANGO_ALLOWED_HOSTS = ${{RAILWAY_PUBLIC_DOMAIN}},${{RAILWAY_PRIVATE_DOMAIN}},healthcheck.railway.app
```

- `RAILWAY_PUBLIC_DOMAIN` — the browser, through Railway's edge.
- `healthcheck.railway.app` — **Railway's health checker sends its own
  Host header**, not the service's domain. Without this entry Django
  answers every check with `400 DisallowedHost` and the deploy fails
  while the application is serving perfectly well.
- `RAILWAY_PRIVATE_DOMAIN` — the Next.js BFF. It strips the incoming
  `Host` (it names the wrong server), so `fetch` sets it from the
  internal URL and Django sees `api.railway.internal`. Without it every
  proxied `/api/v1` and `/_allauth` call answers 400.

## HTTPS redirect vs. the health checker

`prod.py` defaults `SECURE_SSL_REDIRECT` to `True`. Railway's health
checker reaches the container **directly**, not through the edge, so the
request carries no `X-Forwarded-Proto` for `SECURE_PROXY_SSL_HEADER` to
read. Django sees plain HTTP and 301s the check. The checker never sees a
200, the deploy is failed for an unhealthy service that is fine, and
**nothing is logged** — a redirect is not an error.

`prod.py` now exempts the health endpoint, which is what makes the
default survivable:

```python
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
```

Verified both ways on the same commit: redirect on with no exemption ->
healthcheck fails; exemption in place -> `/healthz/` 200 while
`http://.../admin/` still 301s to HTTPS.

This also answers the old document's open question about
`SECURE_PROXY_SSL_HEADER`. The edge does send `X-Forwarded-Proto`. The
health checker does not, and that distinction is the entire bug.

## The BFF must assert the browser's scheme

The BFF dials `http://api.railway.internal:8080` — correctly, since the
private network is already Wireguard-encrypted and has no TLS terminator
to speak HTTPS to. Django then sees a plain-HTTP request and
`SECURE_SSL_REDIRECT` 301s it, and the proxy hands that redirect back to
the browser: an API answering with redirects instead of JSON, again with
nothing logged as an error.

`apps/web/lib/api/proxy.ts` still strips `X-Forwarded-Proto` as an
untrusted caller claim, then re-asserts it from the scheme it actually
served. It is the only party that knows: the browser's TLS terminates
there. Django already reads exactly that header.

## Transactional emails must be built into the API image

The six emails are authored in `packages/emails` and rendered to static
HTML by react-email; Django reads that output at send time. Building the
API image with `apps/api` as its context means the templates can never be
in it, and `EMAILS_DIST_DIR` resolved to a path *above* the app root that
does not exist in a container at all:

```
EmailTemplateMissing: packages/emails/dist/verification.html not found
```

Every transactional email was broken in production — signup, password
reset, invitations, billing notices — while working perfectly in a dev
checkout, where the whole repo is on disk, and in the test suite, where
the same path resolves.

`apps/api/Dockerfile` now builds **from the repository root** and renders
the templates in a Node stage, copying only the resulting HTML (no Node,
no `node_modules`) into the runtime layer. `KEEL_EMAILS_DIST_DIR` points
Django at it. The default still resolves to the repo layout, so dev and
tests are unchanged.

The Railway service must therefore have root directory `/` and Dockerfile
path `apps/api/Dockerfile`.

## `.dockerignore` at the repository root

Both images build from the root, and nothing was excluding anything. The
context was ~600MB, and worse, `COPY . .` dropped the **host's**
`node_modules` and `.venv` on top of the ones installed inside the image
— native binaries built for the wrong platform, and a build failure the
Dockerfile itself does not explain. `apps/api/.dockerignore` only ever
covered the old `apps/api` context.

## Next.js: bind to every interface

Next's standalone server binds `process.env.HOSTNAME || "0.0.0.0"`, and
**Docker sets `HOSTNAME` to the container id**. Without an override the
server binds that single hostname and nothing reaching the container by
IP gets through. The symptom is the app logging `Ready in 189ms` and then
not one request, while the healthcheck fails. `docker run -p` hides it
completely on a local smoke test.

`apps/web/Dockerfile` sets `ENV HOSTNAME=0.0.0.0`.

`apps/web` also needs `output: "standalone"` — and note that
`withContentCollections()` silently drops `output` and
`outputFileTracingRoot` the same way it already drops `headers` and
`rewrites`. `next build` then reports success and emits no
`.next/standalone` at all, leaving the image with nothing to run. Both
are re-applied explicitly in `next.config.ts`.

## Railway blocks the build on dependency CVEs

Railway scans dependencies **before** building and refuses outright:

```
SECURITY VULNERABILITIES DETECTED
  next@15.1.2   Source: pnpm-lock.yaml   Severity: CRITICAL
```

It reads the **root** `pnpm-lock.yaml` regardless of which service is
building, so a frontend CVE blocks the Python API, which never installs
Node. The offender was transitive (`react-email` -> `next@15.1.2`); a
`pnpm.overrides` entry lifts it. Budget for this: a lockfile CVE stops
every deploy in the repo, not just the affected app.

## pgvector — available, no special template

The previous version of this document warned at length that Railway's
managed Postgres does not ship `pgvector`, and that provisioning the
default plugin instead of a `pgvector` template was "the actual risk".
**That is not true.** Against the Postgres Railway provisions today:

```
PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2)
pg_available_extensions: vector | 0.8.6
CREATE EXTENSION -> vector | 0.8.6
```

Image: `ghcr.io/railwayapp-templates/postgres-ssl:18`. Same extension
version as dev's `pgvector/pgvector:pg17`. No template selection needed.

Nothing in Keel uses `pgvector` today; this matters only when something
does.

## Private networking

Services reach each other at `<service>.railway.internal`. Use `http://`,
not `https://` — the traffic is already Wireguard-encrypted, there is no
TLS terminator inside, and internal traffic does not count as egress.

Environments created after October 2025 resolve internal DNS to **both**
IPv4 and IPv6, so `--bind 0.0.0.0` is fine. On a legacy IPv6-only
environment it would not be — that is the case where a service must bind
`::`.

Private networking is runtime-only. It does not exist during a build.

## Migrations

`preDeployCommand`, on `api` only:

```ts
preDeploy: "python manage.py migrate --no-input",
```

Verified: Railway runs it after a successful build and before the start
command, in its own container with the deploy's environment and private
network access. Every app applied cleanly on first deploy and reported
`No migrations to apply` on subsequent ones. A failing pre-deploy aborts
the deploy — the previous one keeps serving.

Only `api` declares it. All services build the same image and would each
run their own copy on every deploy, racing concurrent `migrate` runs.

**Still not tested:** a deliberately-broken migration, and therefore the
rollback story. Django wraps each migration in a transaction on Postgres,
and Railway's dashboard offers one-click redeploy of a previous build, so
rolling the *code* back while leaving the schema forward is the intended
path — but that is reasoning, not evidence.

## Environment variables

Secrets are `preserve()` in `.railway/railway.ts` — they live in Railway,
never in the file. Set them once per environment.

Beyond the hosts and ports above, the ones that actually bite:

| Variable                                | Why                                                                                                                                                                       |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DJANGO_DEBUG`                          | **No default.** `base.py` reads `env("DJANGO_DEBUG")` with no fallback, so omitting it is a hard boot failure, not a safe default.                                         |
| `KEEL_APP_DOMAIN`                       | The **Next.js app's** host, not Django's. Pointing it at the API's own domain trips `keel.core.E004` at boot, because it then has no matching entry in CSRF trusted origins. |
| `DJANGO_CSRF_TRUSTED_ORIGINS`           | The browser-facing origin — the Next.js service — since the BFF forwards the browser's `Origin` unchanged.                                                                 |
| `DJANGO_SECRET_KEY`, `KEEL_ENCRYPTION_KEY` | Generated per environment. A default `SECRET_KEY` is a hard boot failure (`keel.core.checks`).                                                                          |
| `DJANGO_DB_CONN_MAX_AGE=60`             | Railway Postgres has no pooler in front of it, so persistent connections are safe. Leave at `0` for Neon (below).                                                          |
| `KEEL_EMAILS_DIST_DIR`                  | Set by the Dockerfile. Only override it if you relocate the rendered templates.                                                                                            |

`DATABASE_URL` and `REDIS_URL` come from `${{Postgres.DATABASE_URL}}` /
`${{Redis.REDIS_URL}}`; `PORT` and `RAILWAY_GIT_COMMIT_SHA` are set by
Railway.

## Postgres provider neutrality — Railway vs. Neon

`DATABASE_URL` is the only thing `base.py` reads, and no code path
branches on the provider. The pooling settings differ:

- **Railway Postgres** has no pooler in front of it:
  `DJANGO_DB_CONN_MAX_AGE=60`,
  `DJANGO_DB_DISABLE_SERVER_SIDE_CURSORS=false`.
- **Neon**'s default endpoint is PgBouncer in transaction mode: leave
  `DJANGO_DB_CONN_MAX_AGE=0` and set
  `DJANGO_DB_DISABLE_SERVER_SIDE_CURSORS=true`. Session state, including
  server-side cursors, does not survive a pooled transaction boundary.

Both are the repo's defaults, so Neon is safe with nothing set and
Railway is the one that needs the two values above. **The Neon half is
still unverified** — deploying the same commit against both providers and
diffing nothing else has not been done.

## Static files

`whitenoise.middleware.WhiteNoiseMiddleware` plus
`CompressedManifestStaticFilesStorage`; `collectstatic` runs at image
build time. Verified live: a hashed asset served 200 from the Django
admin's own CSS. This covers only what Django renders — Next.js serves
the application's assets.

## Auth cookies without a shared registrable domain

The deploy this document describes runs the app and the API on two
unrelated `*.up.railway.app` hostnames, with `SESSION_COOKIE_DOMAIN`
unset (host-only cookies). Since `docs/adr/0002-auth-bff-shape.md` the
browser only ever talks to the Next.js origin — the BFF forwards to
Django server-side — so a shared registrable domain is not needed for the
browser's session cookie in this configuration.

**Only partially exercised.** `/_allauth/browser/v1/config` and the CSRF
cookie round-trip through the BFF were confirmed; a full authenticated
session was not, because signup was blocked by the two bugs below until
late in the deploy.

A production deployment on a real domain should still put the app and API
on one registrable domain (`acme.com` / `api.acme.com`) and set
`KEEL_APP_DOMAIN` and `DJANGO_SESSION_COOKIE_DOMAIN` accordingly. Vercel
preview deployments on `*.vercel.app` cannot share a `Domain=.acme.com`
cookie; a wildcard preview domain requires Vercel Pro.

## Two application bugs this deploy found

Neither is Railway-specific; both were latent and are now fixed with
regression tests.

1. **Every transactional email 500'd** — the missing templates above.
2. **Signing up with an existing address 500'd.** allauth's
   enumeration-prevention path mails the existing account, and building
   that mail needs `HEADLESS_FRONTEND_URLS["account_signup"]` and
   `["account_reset_password"]`. Neither was configured, so
   `ImproperlyConfigured` propagated as a 500 — meaning the one flow
   whose entire purpose is to be indistinguishable from a fresh signup
   was the only one that returned an error, which is exactly the
   enumeration signal it exists to suppress. It reproduces in the test
   suite the moment anything signs up twice with one address, which
   nothing did.

Also observed, not yet addressed: the failed signup **persisted the user
before the email raised**, so account creation and the verification email
are not in one transaction. A user whose verification mail fails to send
is left in the database, and their next attempt takes the "already
exists" path.

## Cost

Railway bills usage on top of a plan minimum: `$10/GB-RAM/month`,
`$20/vCPU/month`, `$0.05/GB` egress, `$0.15/GB/month` volumes. Hobby is
$5/month, Pro $20/month, each crediting that much usage.

The full seven-resource topology needs Pro. Four always-on API services
at a conservative 0.5 vCPU / 512MB each is roughly $60/month of compute
before the frontend and databases. `worker` and `beat` are idle most of
the time for a low-traffic project and are the first place to look if the
bill runs high — though neither is a good scale-to-zero candidate.

**Still a written estimate, not a measured bill.** The deploy described
here ran for hours, not a billing cycle.

## What remains untested

Each of these needs Pro (for the service slots) or time:

1. `worker` and `beat` deployed, and Celery processing a real job.
2. `stream` deployed, and whether Railway's edge buffers
   `text/event-stream`. `keel/jobs/sse.py` sets `X-Accel-Buffering: no`
   and flushes a leading comment; neither has been checked against
   Railway's proxy. If it buffers, the symptom is a job tray that shows
   nothing for minutes then everything at once.
3. A deliberately-broken migration, and the rollback story.
4. The same commit against Neon instead of Railway Postgres.
5. A full authenticated session and the org-scoped app shell end to end.
6. A real monthly bill.
7. Custom domains and their DNS/TLS step — this deploy used the
   Railway-issued `*.up.railway.app` hostnames throughout.
