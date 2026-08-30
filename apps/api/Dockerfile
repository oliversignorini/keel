# Multi-stage build for the Django API. One image, four Railway services
# (.railway/railway.ts: api, stream, worker, beat) — they differ only in
# startCommand, not in what gets built here.
#
# Built from the *repository root*, not apps/api: the transactional
# emails are authored in packages/emails and rendered to static HTML by a
# Node toolchain, and Django reads that output at send time. With an
# apps/api context they cannot be in the image, and every email raises
# EmailTemplateMissing — signup answers 500 on a real deploy while
# working perfectly in a dev checkout, where the repo tree is on disk.

# --- emails ----------------------------------------------------------------
# react-email renders each template once, here, with its placeholder
# tokens ({{VERIFY_URL}} etc.) left in place. Django substitutes per
# recipient at send time and never invokes Node — see
# keel/notifications/emails.py's module docstring.
FROM node:22-slim AS emails
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH
RUN corepack enable
WORKDIR /repo

# Every workspace manifest must be present before `pnpm install`, or the
# workspace: protocol links cannot resolve.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
COPY packages/api-client/package.json packages/api-client/
COPY packages/cli/package.json packages/cli/
COPY packages/emails/package.json packages/emails/
COPY packages/eslint-config/package.json packages/eslint-config/
COPY packages/tsconfig/package.json packages/tsconfig/
COPY packages/ui/package.json packages/ui/
RUN pnpm install --frozen-lockfile --filter @keel/emails...

COPY packages/emails packages/emails
RUN pnpm --filter @keel/emails build

# --- python deps -----------------------------------------------------------
FROM python:3.12-slim AS builder

# uv is the project's dependency manager (uv.lock is the lockfile CI and
# dev both use) — installing it via the pinned static binary avoids a pip
# bootstrap step and matches what scripts/check_coverage.py's CI job uses.
COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so an app-code-only change doesn't invalidate this
# layer. --no-install-project defers installing the project itself until
# the source is copied, per uv's documented Docker layering pattern.
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/ ./
RUN uv sync --frozen --no-dev

# --- runtime ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

# libpq5 is psycopg[binary]'s runtime dependency; the [binary] extra
# vendors its own libpq, but the base image still needs the shared libs
# libpq5 provides (SSL, locale) for TLS to a real Postgres — sslmode is
# required on both Railway Postgres and Neon, see docs/deploy-railway.md.
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 keel
WORKDIR /app

COPY --from=builder --chown=keel:keel /app /app

# Just the rendered HTML, not Node or node_modules. KEEL_EMAILS_DIST_DIR
# points config/settings/base.py at it, since the repo-relative default
# has no meaning inside an image whose root is the app itself.
COPY --from=emails --chown=keel:keel /repo/packages/emails/dist /opt/keel/emails

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    KEEL_EMAILS_DIST_DIR=/opt/keel/emails

# collectstatic needs a settings module to import but not a live database
# or a real KEEL_ENCRYPTION_KEY/SECRET_KEY — every app's AppConfig.ready()
# was checked (see docs/deploy-railway.md) to be free of DB or crypto calls
# at import time, and django.contrib.staticfiles.collectstatic never
# queries the database. DJANGO_SECRET_KEY and KEEL_ENCRYPTION_KEY keep
# base.py's dev-only defaults for this step; the real values are supplied
# by Railway's environment at container start, not at build time.
RUN python manage.py collectstatic --no-input

USER keel

# No CMD/ENTRYPOINT: .railway/railway.ts sets deploy.startCommand per
# service (gunicorn for api, uvicorn for stream, celery for worker/beat).
# A default here would only be reached by a misconfigured service and
# would silently mask that misconfiguration instead of failing loudly.
