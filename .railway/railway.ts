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

export default defineRailway((ctx) => {
  const db = postgres("Postgres");
  const cache = redis("Redis");

  // All four services build the same apps/api image and differ only in
  // startCommand — see docs/deploy-railway.md "Service topology".
  // IaC defaults the branch to "main"; this repo's default is "master",
  // and the default is not read from GitHub.
  const source = github(REPO, { branch: "master", rootDirectory: "apps/api" });
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
    DJANGO_ALLOWED_HOSTS: "${{RAILWAY_PUBLIC_DOMAIN}}",
    DJANGO_CSRF_TRUSTED_ORIGINS: "https://${{RAILWAY_PUBLIC_DOMAIN}}",
    KEEL_APP_DOMAIN: "${{RAILWAY_PUBLIC_DOMAIN}}",
    SENTRY_ENVIRONMENT: ctx.environment,
    SENTRY_DSN: preserve(),
    RESEND_API_KEY: preserve(),
  };

  const api = service("api", {
    source,
    build,
    watchPatterns,
    start: "gunicorn config.wsgi:application --bind 0.0.0.0:$PORT",
    healthcheck: "/healthz/",
    healthcheckTimeout: 30,
    // Only `api` migrates. All four services deploy on the same push;
    // repeating this would race four concurrent `migrate` runs.
    preDeploy: "python manage.py migrate --no-input",
    deploy: restart,
    env: appEnv,
  });

  // SSE only (keel/jobs/sse.py). Never gunicorn: a held-open SSE
  // connection occupies a sync worker for its whole life.
  const stream = service("stream", {
    source,
    build,
    watchPatterns,
    start: "uvicorn config.asgi_stream:application --host 0.0.0.0 --port $PORT",
    healthcheck: "/healthz/",
    healthcheckTimeout: 30,
    deploy: restart,
    env: appEnv,
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

  return project("keel", {
    resources: [group("Backend", [db, cache, api, stream, worker, beat])],
  });
});
