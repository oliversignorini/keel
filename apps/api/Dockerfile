# Multi-stage build for the Django API. One image, four Railway services
# (infra/railway.json: api, stream, worker, beat) — they differ only in
# startCommand, not in what gets built here.
#
# Not directly verified against a live Railway build (docs/deploy-railway.md
# carries the same epistemic-status note as the rest of that file) — built
# and run locally against infra/compose.dev.yml's Postgres/Redis, see
# docs/deploy-railway.md "Dockerfile" section for the exact commands.

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
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

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

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# collectstatic needs a settings module to import but not a live database
# or a real KEEL_ENCRYPTION_KEY/SECRET_KEY — every app's AppConfig.ready()
# was checked (see docs/deploy-railway.md) to be free of DB or crypto calls
# at import time, and django.contrib.staticfiles.collectstatic never
# queries the database. DJANGO_SECRET_KEY and KEEL_ENCRYPTION_KEY keep
# base.py's dev-only defaults for this step; the real values are supplied
# by Railway's environment at container start, not at build time.
RUN python manage.py collectstatic --no-input

USER keel

# No CMD/ENTRYPOINT: infra/railway.json sets deploy.startCommand per
# service (gunicorn for api, uvicorn for stream, celery for worker/beat).
# A default here would only be reached by a misconfigured service and
# would silently mask that misconfiguration instead of failing loudly.
