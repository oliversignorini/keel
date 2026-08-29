# Multi-stage build for the Next.js app.
#
# Built from the repository root, not apps/web: the app depends on
# workspace packages (@keel/ui, @keel/api-client) that live outside its
# own directory, so the build context has to span the whole monorepo.
# Railway's service is configured with rootDirectory "/" and
# dockerfilePath "apps/web/Dockerfile" to match (.railway/railway.ts).
#
# Output is Next's `standalone` build (next.config.ts) — the runtime stage
# carries a traced node_modules containing only what the server actually
# imports, instead of the ~1GB the full pnpm workspace install produces.

FROM node:22-slim AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app

# --- deps ------------------------------------------------------------------
# Manifests only, so a source-only change doesn't reinstall the world.
# Every workspace package's package.json must be present before
# `pnpm install`, or pnpm cannot resolve the workspace: protocol links.
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
COPY packages/api-client/package.json packages/api-client/
COPY packages/cli/package.json packages/cli/
COPY packages/emails/package.json packages/emails/
COPY packages/eslint-config/package.json packages/eslint-config/
COPY packages/tsconfig/package.json packages/tsconfig/
COPY packages/ui/package.json packages/ui/
RUN pnpm install --frozen-lockfile

# --- build -----------------------------------------------------------------
FROM base AS builder
COPY --from=deps /app ./
COPY . .
# NEXT_PUBLIC_* are inlined into the browser bundle at build time, not
# read at runtime — a Railway variable set only on the service is
# invisible to them. They are declared as build args here so the values
# reach `next build`; see .railway/railway.ts for which ones are set.
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_BILLING_CREDITS
ARG NEXT_PUBLIC_POSTHOG_KEY
ARG NEXT_PUBLIC_POSTHOG_HOST
ARG NEXT_PUBLIC_SENTRY_DSN
ARG RAILWAY_GIT_COMMIT_SHA
RUN pnpm --filter web build

# --- runtime ---------------------------------------------------------------
FROM base AS runtime
ENV NODE_ENV=production
# node:22-slim already ships a non-root `node` user at uid 1000, so this
# reuses it rather than adding one (`useradd --uid 1000` fails outright:
# "UID 1000 is not unique"). The API image builds from python:3.12-slim,
# where 1000 is free, which is why it creates its own.

# The standalone bundle keeps the workspace's directory layout, so the
# server entrypoint sits at apps/web/server.js inside it.
COPY --from=builder --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=builder --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static

USER node

# No CMD: .railway/railway.ts sets the start command, the same way the
# API image leaves it to the service definition.
