# Maintenance

Supported versions, update cadence, and the checklist for a Django major
upgrade. Written for whoever owns this repo after the initial build —
including a future agent working from `CLAUDE.md`.

## Supported versions

| Component  | Version this repo targets        | Where it's pinned                                                                                                                               |
| ---------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Python     | 3.12+                            | `apps/api/pyproject.toml` `requires-python`, enforced at runtime by the floor check in `apps/api/config/settings/base.py`                       |
| Django     | 6.0+ (currently resolves to 6.1) | `apps/api/pyproject.toml` (`django~=6.0`), enforced by the same floor check                                                                     |
| Node.js    | 22+                              | root `package.json` `engines.node`                                                                                                              |
| pnpm       | 9.5.0                            | root `package.json` `packageManager` (corepack-pinned)                                                                                          |
| PostgreSQL | 17                               | `infra/compose.dev.yml` / `infra/compose.prod.yml` (`pgvector/pgvector:pg17`); see `docs/deploy-railway.md` for the hosted-provider equivalents |
| Redis      | 7                                | `infra/compose.dev.yml` / `infra/compose.prod.yml` (`redis:7`)                                                                                  |

`~=6.0` on Django is deliberate: it floats within the 6.x series (picking
up 6.1, 6.2, …) but will not silently jump to a 7.0 major, which is exactly
the boundary the upgrade checklist below exists for.

## Update cadence

- **Python/Node patch and minor releases** — apply opportunistically, no
  fixed schedule. Neither has broken this codebase across a minor bump
  historically.
- **Django and DRF** — check for a new minor release monthly; Django's own
  security-release calendar (published ahead of time on
  [djangoproject.com](https://www.djangoproject.com/download/)) takes
  priority over the monthly cadence — apply a security release within the
  week it ships, not at the next scheduled check.
- **Dependencies generally (`uv.lock`, `pnpm-lock.yaml`)** — `docs/plans/phase-9.md`'s 9.A
  slice adds `.github/dependabot.yml` for pip/npm/github-actions/docker,
  weekly, grouped minor+patch. Once that lands, Dependabot PRs are the
  cadence; this section stops being the mechanism and starts being the
  record of what it covers.
- **PostgreSQL and Redis major versions** — no fixed schedule. Bump when
  the hosting provider (Railway, Neon) deprecates the running major, or
  when a feature this repo wants (e.g. a newer `pgvector` release) needs
  it. Test `CREATE EXTENSION vector;` against the new image before cutting
  over — see `docs/deploy-railway.md`'s pgvector section for the last
  version actually verified.

## Django upgrade checklist

Run this for every Django minor bump (6.0 → 6.1, 6.1 → 6.2, …); a major
bump (6.x → 7.0) additionally needs a manual read of Django's own release
notes for removed features before starting.

1. Read the release notes for the target version — Django's own
   [release notes index](https://docs.djangoproject.com/en/stable/releases/) —
   specifically the "Backwards incompatible changes" and "Deprecated
   features" sections.
2. Bump `django~=X.Y` in `apps/api/pyproject.toml`, run `uv lock`, and let
   `uv sync` resolve the rest of the dependency graph (`django-allauth`,
   `djangorestframework`, `drf-spectacular`, `django-stubs` all pin ranges
   against Django — a resolver conflict here is the checklist doing its
   job, not a bug).
3. Run the full test suite locally (`uv run pytest` from `apps/api`) before
   touching CI — this repo's coverage floors (`[tool.keel.coverage]` in
   `pyproject.toml`) mean a version bump that changes ORM behavior under
   the hood shows up as a red test, not a silent regression.
4. Run `python manage.py check --deploy` under `config.settings.prod`
   locally (see `.github/workflows/ci.yml`'s `test-api` job, once
   `docs/plans/phase-9.md` 9.C lands it, for the exact invocation and
   required env vars) — a new Django release occasionally adds a new
   deploy check.
5. Regenerate the OpenAPI schema and the TS client
   (`scripts/merge_openapi.py`, then orval) — a Django/DRF/drf-spectacular
   bump can change generated schema shape even with no application code
   changes. The `api-client-generation` CI job fails on drift; do this
   locally first so the diff is reviewable instead of a surprise.
6. Read `apps/api/keel/**/migrations/` for anything the new Django version
   wants to add (e.g. a new default `Meta` option triggers an empty
   migration). An unexplained migration appearing after nothing but a
   dependency bump is expected; commit it with a message that says so.
7. Deploy to a non-production environment first if one exists; otherwise
   treat the Railway `preDeployCommand` migration step
   (`docs/deploy-railway.md` "Migration strategy") as the first real test
   and have the rollback path ready before triggering the deploy.

## Node / Next.js upgrade checklist

Shorter, because this repo carries much less Next.js-version-specific
logic than Django-version-specific logic:

1. Bump the version in `apps/web/package.json`, run `pnpm install`.
2. `pnpm --filter web typecheck` and `pnpm --filter web lint` first — a
   Next.js major most often breaks types before it breaks runtime.
3. `pnpm --filter web build` locally — confirms the production build path,
   which `pnpm dev` does not exercise.
4. Run the Playwright suites (`apps/web/e2e/`,
   `playwright.cross-host.config.ts`) — the cross-host config specifically
   exercises the `app.lvh.me` / `lvh.me` / `api.lvh.me` cookie-sharing
   behavior described in `docs/auth-flow.md`, which a Next.js middleware
   or routing change is the most likely thing to break silently.
