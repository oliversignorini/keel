// Railway Infrastructure as Code — the project's single source of truth.
//
// This replaces infra/railway.json. Railway deprecated Config as Code
// (railway.json / railway.toml): new services cannot opt into it at all,
// and existing files stop being read on 2026-12-01. Config as Code was
// also per-*service* — the `{ "services": { ... } }` shape the old file
// used was never a schema Railway read. IaC is per-*project*, which is
// what a four-service topology plus its databases actually needs.
//
//   railway config plan    # preview
//   railway config apply   # apply after confirmation
//
// Secrets are `preserve()`: they live in Railway, never in this file.
// Set them once per environment (dashboard or `railway variables --set`):
//   DJANGO_SECRET_KEY, KEEL_ENCRYPTION_KEY, RESEND_API_KEY, SENTRY_DSN,
//   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, POSTHOG_PROJECT_API_KEY,
//   GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET

import {
  defineRailway,
  github,
  group,
  postgres,
  preserve,
  project,
  redis,
  service,
} from "railway/iac";

const REPO = "oliversignorini/keel";
// IaC defaults the branch to "main"; this repo's default is "master",
// and the default is not read from GitHub. KEEL_RAILWAY_BRANCH overrides
// it so a branch can be deployed and smoke-tested before it lands.
const BRANCH = process.env.KEEL_RAILWAY_BRANCH ?? "master";

// Pinned rather than left to Railway's per-service $PORT — see the note
// on api's start command below.
const API_PORT = "8080";
const STREAM_PORT = "8081";

export default defineRailway((ctx) => {
  const db = postgres("Postgres");
  const cache = redis("Redis");

  // All four services build the same apps/api image and differ only in
  // startCommand — see docs/deploy-railway.md "Service topology".
  const source = github(REPO, { branch: BRANCH, rootDirectory: "apps/api" });
  const build = { builder: "DOCKERFILE" as const, dockerfilePath: "Dockerfile" };
  const watchPatterns = ["/apps/api/**"];
  // restartPolicy* are only read under `deploy` — as top-level service
  // keys they are silently dropped.
  const restart = { restartPolicyType: "ON_FAILURE" as const, restartPolicyMaxRetries: 5 };

  // Every variable Django reads that is neither a secret nor a Railway
  // reference. DJANGO_DEBUG has no default in config/settings/base.py —
  // omitting it is a boot failure, not a fallback to False.
  const appEnv = {
    DJANGO_DEBUG: "false",
    DJANGO_SECRET_KEY: preserve(),
    KEEL_ENCRYPTION_KEY: preserve(),

    DATABASE_URL: db.env.DATABASE_URL,
    REDIS_URL: cache.env.REDIS_URL,
    CELERY_BROKER_URL: cache.env.REDIS_URL,

    // Railway Postgres has no pooler in front of it, so a persistent
    // connection is safe and worth the saved handshake. Neon's pooled
    // endpoint needs the opposite — see docs/deploy-railway.md "Pooling".
    DJANGO_DB_CONN_MAX_AGE: "60",
    DJANGO_DB_DISABLE_SERVER_SIDE_CURSORS: "false",

    DJANGO_SECURE_SSL_REDIRECT: "true",

    // Defaults to the Railway-generated *.up.railway.app hostname so a
    // first deploy is reachable before DNS exists. A real deployment
    // overrides all three with the custom domain — and must, because the
    // session cookie has to be shared with the Next.js app on the same
    // registrable domain (docs/deploy-railway.md "Auth cookie domain").
    // healthcheck.railway.app is the Host header Railway's own health
    // checker sends — not the service's domain. Without it Django answers
    // the check with 400 DisallowedHost and every deploy fails its
    // healthcheck while the app is running perfectly well.
    DJANGO_ALLOWED_HOSTS: "${{RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app",
    KEEL_APP_DOMAIN: "${{RAILWAY_PUBLIC_DOMAIN}}",
    // CSRF is validated against the browser-facing origin, which is the
    // Next.js app, not this service — the BFF forwards the Origin it
    // received (docs/adr/0002-auth-bff-shape.md).
    DJANGO_CSRF_TRUSTED_ORIGINS: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
    KEEL_FRONTEND_URL: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
    KEEL_APP_FRONTEND_URL: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
    SENTRY_ENVIRONMENT: ctx.environment,
    SENTRY_DSN: preserve(),
    RESEND_API_KEY: preserve(),
  };

  const api = service("api", {
    source,
    build,
    watchPatterns,
    // The port is literal, not $PORT. Railway execs the start command
    // without a shell, so $PORT arrives at gunicorn as four literal
    // characters — "'$PORT' is not a valid port number", then a
    // crashloop. Wrapping it in `sh -c` does not help; the wrapper is
    // not given a shell either. Since the BFF has to dial a known port
    // on api.railway.internal anyway, the number is pinned here and PORT
    // is set to match so Railway's own port detection agrees.
    start: `gunicorn config.wsgi:application --bind 0.0.0.0:${API_PORT}`,
    healthcheck: "/healthz/",
    healthcheckTimeout: 30,
    // Only `api` migrates. All four services deploy on the same push;
    // repeating this would race four concurrent `migrate` runs.
    preDeploy: "python manage.py migrate --no-input",
    deploy: restart,
    // Railway assigns $PORT per service, but the Next.js BFF has to dial
    // a *known* port on api.railway.internal — so pin it rather than
    // letting it float.
    env: { ...appEnv, PORT: API_PORT },
  });

  // SSE only (keel/jobs/sse.py). Never gunicorn: a held-open SSE
  // connection occupies a sync worker for its whole life.
  const stream = service("stream", {
    source,
    build,
    watchPatterns,
    start: `uvicorn config.asgi_stream:application --host 0.0.0.0 --port ${STREAM_PORT}`,
    healthcheck: "/healthz/",
    healthcheckTimeout: 30,
    deploy: restart,
    env: { ...appEnv, PORT: STREAM_PORT },
  });

  const worker = service("worker", {
    source,
    build,
    watchPatterns,
    start: "celery -A config worker -l info -Q default,email,external,scheduled",
    deploy: restart,
    env: appEnv,
  });

  const beat = service("beat", {
    source,
    build,
    watchPatterns,
    start: "celery -A config beat -l info",
    deploy: restart,
    env: appEnv,
  });

  // The Next.js app. Built from the repository root, not apps/web: it
  // depends on workspace packages that live outside its own directory.
  // Its BFF reaches api and stream over the private network, so neither
  // of those hops crosses the public internet or counts as egress.
  const web = service("web", {
    source: github(REPO, { branch: BRANCH }),
    build: { builder: "DOCKERFILE" as const, dockerfilePath: "apps/web/Dockerfile" },
    watchPatterns: ["/apps/web/**", "/packages/**"],
    start: "node apps/web/server.js",
    healthcheck: "/",
    healthcheckTimeout: 30,
    deploy: restart,
    env: {
      // Server-only (ADR 0002) — the browser never learns Django's
      // address. http, not https: private traffic is already Wireguard
      // encrypted, and there is no TLS terminator inside the network.
      KEEL_API_INTERNAL_URL: `http://api.railway.internal:${API_PORT}`,
      KEEL_API_STREAM_INTERNAL_URL: `http://stream.railway.internal:${STREAM_PORT}`,
      NEXT_PUBLIC_SITE_URL: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
      NEXT_PUBLIC_BILLING_CREDITS: "false",
    },
  });

  return project("keel", {
    resources: [group("Backend", [db, cache, api, stream, worker, beat]), web],
  });
});
