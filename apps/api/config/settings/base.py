"""Base settings, shared by every environment. Reads configuration from env.

Env-config library: django-environ. Chosen over python-decouple because it
also parses DATABASE_URL / REDIS_URL / CACHE_URL into the dict shapes
Django's DATABASES/CACHES settings expect (env.db(), env.cache()), which
removes a class of hand-rolled URL-parsing bugs that a plain decouple-style
config() call would otherwise need helpers for.
"""

import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import django
import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
# Read apps/api/.env, then fall back to the repo-root .env.
#
# .env.example lives at the repo root, so "copy .env.example to .env" puts
# the file there — and Django, whose BASE_DIR is apps/api, would not see it.
# The symptom is a DisallowedHost 400 with settings that look correct on
# disk, which is a genuinely confusing half-hour. Accept both locations;
# apps/api wins where both exist, so a per-app override still works.
_ENV_CANDIDATES = (BASE_DIR / ".env", BASE_DIR.parent.parent / ".env")
for _env_file in _ENV_CANDIDATES:
    if _env_file.is_file():
        environ.Env.read_env(_env_file)
        break

# --- Version floor -----------------------------------------------------
# A project that needs an older Django or Python is a fork, not a
# configuration (PRD §8).
if sys.version_info < (3, 12):  # noqa: UP036 - a floor assertion, not dead code
    raise RuntimeError("Keel requires Python 3.12 or newer.")
if django.VERSION < (6, 0):
    raise RuntimeError("Keel requires Django 6.0 or newer.")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# --- MFA scaffold flag (PRD §8) --------------------------------------------
# TOTP is wired but off by default. Flip to true to install allauth.mfa
# (and thereby its headless endpoints, gated on apps.is_installed — see
# allauth.headless.urls.build_urlpatterns) without generating a migration
# for it: the app's own migrations ship in the package.
KEEL_MFA_ENABLED = env.bool("KEEL_MFA_ENABLED", default=False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.sites",
    # Third party
    "corsheaders",
    # Serves Swagger UI assets for /api/v1/docs from local static instead
    # of cdn.jsdelivr.net — keeps the docs working offline and inside
    # embedded browsers that block third-party CDN scripts.
    "ninja",
    # allauth headless (PRD §4 "Auth architecture", §8)
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.usersessions",
    # Keel apps
    "keel.core",
    "keel.accounts",
    "keel.organizations",
    "keel.billing",
    "keel.connections",
    "keel.jobs",
    "keel.audit",
    "keel.notifications",
    "keel.files",
    "keel.widgets",
]

if KEEL_MFA_ENABLED:
    INSTALLED_APPS.append("allauth.mfa")

# allauth requires the sites framework; headless mode never renders a
# templated page from it, but the app must be present.
SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Django 6's native CSP middleware — reads
    # SECURE_CSP above. Placed early per Django's own middleware-ordering
    # guidance for security headers.
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "keel.core.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Rate limiting over every /api/v1/ request (PRD §3 NFR "Security") —
    # after AuthenticationMiddleware so request.user is populated for
    # UserRateThrottle, and applied uniformly regardless of which auth
    # callable (or none, for a public router) the route underneath uses.
    "keel.core.throttle.ThrottleMiddleware",
    "keel.core.middleware.ImpersonationMiddleware",
    "keel.core.idempotency.IdempotencyKeyMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    # Port 5433: infra/compose.dev.yml publishes Postgres there, not 5432 —
    # see the comment on that file for why.
    "default": env.db(
        "DATABASE_URL",
        default="postgres://keel:keel@localhost:5433/keel",
    ),
}

CACHES = {
    "default": env.cache("REDIS_URL", default="redis://localhost:6379/0"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

# --- Celery --------------------------------------------------------------
CELERY_BROKER_URL = env(
    "CELERY_BROKER_URL", default=env("REDIS_URL", default="redis://localhost:6379/0")
)
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_DEFAULT_QUEUE = "default"

# At-least-once delivery, to match code that is written for it (ddia#13):
# Celery's default is ack-before-execute, so a worker killed mid-job
# (deploy, OOM, spot reclaim) loses the message outright and run_job's
# resumability never gets a chance to fire. task_reject_on_worker_lost
# requeues a message whose worker died instead of leaving it stuck
# unacked; visibility_timeout bounds how long a Redis-broker message stays
# invisible before being redelivered, set comfortably above the longest
# job this template's demo job types run (a real project should raise
# this to its own max job duration).
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 60 * 60 * 6}

# Tier 2 jobs (PRD §5.5.4, §5.5.5) — the per-organisation concurrency
# limit enforced by keel/jobs/concurrency.py's Redis semaphore, and the
# Redis connection pub/sub publication and the SSE endpoint both use.
# Separate from CELERY_BROKER_URL in name only, so a project that moves
# Celery onto a managed broker can still point job pub/sub at its own
# Redis instance without another setting name to invent later.
JOBS_MAX_CONCURRENT_PER_ORG = env.int("JOBS_MAX_CONCURRENT_PER_ORG", default=3)
JOBS_REDIS_URL = env("JOBS_REDIS_URL", default=CELERY_BROKER_URL)

# The six scheduled jobs (PRD §5 "Scheduled jobs"). Each is idempotent
# when run twice — see keel/jobs/tasks.py and
# its tests, which run every job twice and assert identical state.
CELERY_BEAT_SCHEDULE = {
    "sync-stripe-plans": {
        "task": "keel.jobs.tasks.sync_stripe_plans_task",
        "schedule": crontab(hour=2, minute=0),  # daily
    },
    "expire-invitations": {
        "task": "keel.jobs.tasks.expire_invitations_task",
        "schedule": crontab(minute=0),  # hourly
    },
    "send-trial-ending-notices": {
        "task": "keel.jobs.tasks.send_trial_ending_notices_task",
        "schedule": crontab(hour=3, minute=0),  # daily
    },
    "check-dunning": {
        "task": "keel.jobs.tasks.check_dunning_task",
        "schedule": crontab(hour=4, minute=0),  # daily
    },
    "purge-old-audit-logs": {
        "task": "keel.jobs.tasks.purge_old_audit_logs_task",
        "schedule": crontab(day_of_week=0, hour=5, minute=0),  # weekly
    },
    "cleanup-expired-sessions": {
        "task": "keel.jobs.tasks.cleanup_expired_sessions_task",
        "schedule": crontab(hour=1, minute=0),  # daily
    },
    # Hardening-slice additions (ddia#7, ddia#13) — see keel/billing/tasks.py
    # and keel/jobs/runner.py for why each sweep exists.
    "sweep-unprocessed-stripe-events": {
        "task": "keel.billing.tasks.sweep_unprocessed_stripe_events",
        "schedule": crontab(minute="*/5"),
    },
    "sweep-stuck-jobs": {
        "task": "keel.jobs.runner.sweep_stuck_jobs_task",
        "schedule": crontab(minute="*/15"),
    },
    # ddia#21 — expires abandoned pending uploads and retries
    # any tombstoned row whose storage object wasn't purged yet.
    "sweep-stale-file-uploads": {
        "task": "keel.files.tasks.sweep_stale_uploads",
        "schedule": crontab(minute="*/15"),
    },
    # ddia#4, ddia#10 — see keel/billing/tasks.py.
    "check-credit-balances": {
        "task": "keel.billing.tasks.check_credit_balances_task",
        "schedule": crontab(hour=6, minute=0),  # nightly, report-only
    },
    "prune-stripe-event-payloads": {
        "task": "keel.billing.tasks.prune_stripe_event_payloads",
        "schedule": crontab(day_of_week=0, hour=6, minute=30),  # weekly
    },
}

# --- Cookies, CORS, CSRF (PRD §4 "Auth architecture", §10 first named risk) -
# Session transport is an HttpOnly cookie, not a JWT (PRD §4). The cookie's
# Domain must be the *registrable* domain — `.acme.com` — so it is shared
# between the web origin (apex `acme.com` for marketing/auth, `app.acme.com`
# for the app shell — plan 6.A) and `api.acme.com` (Django). KEEL_APP_DOMAIN
# is the app's own host (e.g. `app.acme.com`, or `app.lvh.me` in dev, per
# plan 6.A — NOT the registrable domain), so
# keel.core.checks.check_session_cookie_domain genuinely exercises its
# subdomain branch rather than being satisfied by domain equality.
# SESSION_COOKIE_DOMAIN is derived from it rather than duplicated, so the
# two cannot drift apart in an env file. Local dev with no subdomain split
# serves both sides off "localhost" with no port-spanning cookie issue, so
# KEEL_APP_DOMAIN defaults there and SESSION_COOKIE_DOMAIN is left unset
# (host-only cookie) unless a real domain is configured — Chrome rejects
# `Domain=localhost` cookies set with a leading dot.
KEEL_APP_DOMAIN = env("KEEL_APP_DOMAIN", default="localhost")
# The registrable domain is KEEL_APP_DOMAIN itself, unless it is the
# `app.` subdomain plan 6.A introduces, in which case the cookie must be
# scoped one level up (`app.acme.com` -> `.acme.com`) so it is also sent
# to the apex and to `api.*`. Set DJANGO_SESSION_COOKIE_DOMAIN explicitly
# for any shape this heuristic does not cover.
_registrable_domain = (
    KEEL_APP_DOMAIN.removeprefix("app.") if KEEL_APP_DOMAIN.startswith("app.") else KEEL_APP_DOMAIN
)
SESSION_COOKIE_DOMAIN = env(
    "DJANGO_SESSION_COOKIE_DOMAIN",
    default=None if KEEL_APP_DOMAIN == "localhost" else f".{_registrable_domain}",
)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "sessionid"

CSRF_COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN
CSRF_COOKIE_HTTPONLY = False  # the SPA reads this cookie to set the CSRF header
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000"])

# No wildcard: credentialed CORS (CORS_ALLOW_CREDENTIALS=True) forbids
# `Access-Control-Allow-Origin: *` outright, and the browser's console
# message for that failure does not say so — django-cors-headers would
# silently reflect every origin if CORS_ALLOWED_ORIGIN_REGEXES or
# CORS_ALLOW_ALL_ORIGINS were used here instead of an explicit list.
#
# Empty by default (docs/adr/0002-auth-bff-shape.md): since the Next.js
# BFF terminates every `/api/v1/…` and `/_allauth/…` call server-side and
# forwards it itself, no browser `fetch()`/`XMLHttpRequest` should ever
# reach this origin directly with credentials — CORS exists here purely
# as defense in depth against a call site that bypasses the proxy by
# mistake, not as the mechanism that lets the app work. Set
# DJANGO_CORS_ALLOWED_ORIGINS only for a deployment that still needs a
# browser to call this API directly (see the ADR's note on what a
# Railway deployment needs before doing that in production).
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# --- Email (Mailpit in dev, see infra/compose.dev.yml) ---------------------
# ``MAILERS``, not the flat ``EMAIL_*`` settings: Django 6 deprecated
# EMAIL_BACKEND/EMAIL_HOST/EMAIL_PORT/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD/
# EMAIL_USE_TLS (RemovedInDjango70Warning) and refuses to start if any of
# them is defined alongside MAILERS (django.conf's
# ``DEPRECATED_EMAIL_SETTINGS`` check) — so this is an all-or-nothing
# switch, not an additive one. The env var names are unchanged; only the
# shape they land in moved. The base entry is the dev/CI one (Mailpit over
# plain SMTP on :1025); config/settings/test.py and prod.py replace the
# ``default`` mailer's BACKEND with locmem and Resend respectively.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("EMAIL_HOST", default="localhost"),
            "port": env.int("EMAIL_PORT", default=1025),
            "username": env("EMAIL_HOST_USER", default=""),
            "password": env("EMAIL_HOST_PASSWORD", default=""),
            "use_tls": env.bool("EMAIL_USE_TLS", default=False),
        },
    }
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@keel.local")

# Resend (PRD §5). Blank in dev/test, same
# pattern as STRIPE_SECRET_KEY above — keel.notifications.resend_backend
# raises ImproperlyConfigured if a send is actually attempted without it.
# Only wired as the ``default`` mailer's BACKEND in prod.py; dev/test keep
# sending through Mailpit / locmem via the stock Django backends.
# Where keel/notifications/emails.py reads the react-email build output
# from. Defaults to the repo layout, which is what a dev checkout and the
# test suite both have. A container image has no repo above the app, so
# apps/api/Dockerfile builds the templates in a Node stage, copies just
# the rendered HTML in, and points this at it — without the override,
# every transactional email raises EmailTemplateMissing at send time and
# signup answers 500.
KEEL_EMAILS_DIST_DIR = env(
    "KEEL_EMAILS_DIST_DIR",
    default=str(BASE_DIR.parent.parent / "packages" / "emails" / "dist"),
)

RESEND_API_KEY = env("RESEND_API_KEY", default="")

# R2 presigned direct upload (PRD §5). No R2
# credentials exist for this project — dev points ``R2_ENDPOINT_URL`` at
# the MinIO container in infra/compose.dev.yml (S3-API-compatible), and
# tests use ``moto``'s mocked S3 (keel/files/tests/test_uploads.py). Prod
# points these at real Cloudflare R2 credentials; the adapter code
# (keel.files.storage.S3CompatibleStorage) is unchanged either way — R2
# and MinIO both speak the S3 API, so this is purely a settings swap.
R2_ENDPOINT_URL = env("R2_ENDPOINT_URL", default="http://localhost:9000")
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", default="minioadmin")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", default="minioadmin")
R2_BUCKET = env("R2_BUCKET", default="keel-dev")
R2_PUBLIC_URL = env("R2_PUBLIC_URL", default="http://localhost:9000/keel-dev")

# --- Storage seam (docs/storage.md) -----------------------------------------
# ``STORAGES["files"]`` selects the adapter keel.files.services/views call
# through keel.files.storage.get_storage() — never a concrete provider
# import. Flip KEEL_FILES_STORAGE_BACKEND alone (no OPTIONS edit, no code
# change) to move between:
#   - keel.files.storage.S3CompatibleStorage  (MinIO / R2 / real S3 — the
#     default; OPTIONS below point it at MinIO in dev, R2 in prod, both
#     via the R2_* variables above)
#   - keel.files.storage.LocalFileSystemStorage (plain disk under
#     MEDIA_ROOT — for a developer who doesn't want to run MinIO; see
#     that class's docstring for what its "presigned" URL actually is)
KEEL_FILES_STORAGE_BACKEND = env(
    "KEEL_FILES_STORAGE_BACKEND", default="keel.files.storage.S3CompatibleStorage"
)
STORAGES = {
    # Django's own default — nothing in this codebase uses
    # django.core.files.storage.default_storage (file uploads go through
    # the "files" alias below instead), but STORAGES is an all-or-nothing
    # setting: defining the dict at all means "default" must be present
    # too, or FileField's default storage silently disappears.
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "files": {
        "BACKEND": KEEL_FILES_STORAGE_BACKEND,
        # Consumed only by S3CompatibleStorage; LocalFileSystemStorage's
        # constructor accepts and ignores these (its own OPTIONS shape —
        # just "root" — is unrelated), which is what makes switching the
        # BACKEND line alone sufficient.
        "OPTIONS": {
            "endpoint_url": R2_ENDPOINT_URL,
            "access_key_id": R2_ACCESS_KEY_ID,
            "secret_access_key": R2_SECRET_ACCESS_KEY,
            "bucket": R2_BUCKET,
        },
    },
}

MEDIA_ROOT = BASE_DIR / "media"

# Service-layer upload policy — enforces size and content-type limits at
# the service layer, configurably — checked
# against both the client's declared values at create time and the
# storage provider's observed HeadObject values at complete time
# (ddia#21) — so a client can't declare a small size to pass the create
# check and then upload something larger. Empty allowlist means "no
# content-type restriction"; a real deployment sets this to the document
# types it actually accepts.
FILES_MAX_UPLOAD_SIZE_BYTES = env.int("FILES_MAX_UPLOAD_SIZE_BYTES", default=100 * 1024 * 1024)
FILES_ALLOWED_CONTENT_TYPES = env.list("FILES_ALLOWED_CONTENT_TYPES", default=[])

# keel.files.tasks.sweep_stale_uploads (ddia#21's "beat sweeper for stale
# pending rows") expires a pending upload nobody ever completed after
# this many seconds.
FILES_PENDING_UPLOAD_TTL_SECONDS = env.int("FILES_PENDING_UPLOAD_TTL_SECONDS", default=60 * 60 * 24)

# Audit log retention (PRD §5 "Scheduled jobs") —
# keel.audit.services.purge_old_audit_logs, run weekly.
AUDIT_LOG_RETENTION_DAYS = env.int("AUDIT_LOG_RETENTION_DAYS", default=365)

# --- Encryption (keel/core/crypto.py) ---------------------------------
# Backs Connection.access_token / refresh_token. Generate a key with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#
# One env var, comma-separated when rotating (ddia#27): django-environ's
# env.list() already splits on comma, so a single key
# (KEEL_ENCRYPTION_KEY=<key>) and multiple
# (KEEL_ENCRYPTION_KEY=<new-key>,<old-key>) both parse without a second
# setting name to introduce. keel.core.crypto wraps this in a
# cryptography.fernet.MultiFernet — the first key encrypts every new
# value, every key can decrypt, so rotating means prepending a new key
# rather than losing the ability to read what the old one wrote.
# `python manage.py rotate_connection_tokens` (keel/connections/management)
# re-encrypts every Connection row under the first (newest) key once a
# rotation has added one.
KEEL_ENCRYPTION_KEYS = env.list("KEEL_ENCRYPTION_KEY", default=[])

# --- General API rate limiting -------------------------------------------
# PRD §3 NFR "Security": "Rate limiting ... on the API generally".
# allauth's own limiter already covers
# /_allauth/* — this is everything else. Read by keel.core.throttle's
# ThrottleMiddleware, applied ahead of routing to every /api/v1/ request.
# Django's cache (Redis, PRD §3 "Redis for ... rate limit counters") backs
# the counters. `None` disables a throttle entirely (config/settings/test.py).
KEEL_API_THROTTLE_USER_RATE: str | None = env("KEEL_API_THROTTLE_USER_RATE", default="300/minute")
KEEL_API_THROTTLE_ANON_RATE: str | None = env("KEEL_API_THROTTLE_ANON_RATE", default="60/minute")

# How many *trusted* proxies sit in front of this process and append to
# ``X-Forwarded-For``. This is the throttle's client-identity rule, so it
# is security-relevant: `X-Forwarded-For` is a client-supplied header, and
# an anon bucket keyed off it is no bucket at all — a browser that varies
# the header per request gets a fresh anon allowance every time. Default
# 0: ignore the header entirely and key on ``REMOTE_ADDR``, which only the
# socket peer can choose. Set it to the number of proxies that actually
# rewrite/append the header on the way in (the Next.js BFF strips every
# client-supplied `x-forwarded-*` before forwarding — apps/web/lib/api/
# proxy.ts — so on Railway the count is the edge plus that hop) and the
# nth-from-the-right entry, the last one a trusted proxy wrote, becomes
# the identity. Misconfiguring it high is a bypass, so it stays opt-in.
KEEL_API_THROTTLE_NUM_PROXIES: int = env.int("KEEL_API_THROTTLE_NUM_PROXIES", default=0)

# --- allauth headless (PRD §4 "Auth architecture", §8) ---------------------
# `HEADLESS_ONLY = True`: no allauth template-rendered account views, only
# the JSON API at /_allauth/. The account app's own login/signup URLs
# (accounts/) are still included in config/urls.py because the OAuth
# handshake redirect needs somewhere headed to land.
HEADLESS_ONLY = True
# Only the browser (cookie + CSRF) client is served — PRD §4: "the
# X-Session-Token header path exists for non-browser clients and stays
# unused." Pinning to one client also collapses the `{client}` path
# parameter out of allauth's generated OpenAPI spec (A.3), which is what
# keeps the merged spec's paths matching docs/auth-client-contract.md.
HEADLESS_CLIENTS = ("browser",)
# Enables allauth's /_allauth/openapi.json — read directly by
# scripts/merge_openapi.py (A.3), not served to end users.
HEADLESS_SERVE_SPECIFICATION = True
FRONTEND_URL = env("KEEL_FRONTEND_URL", default="http://localhost:3000")
# Same origin as FRONTEND_URL unless KEEL_APP_FRONTEND_URL says otherwise
# (plan 6.A splits the app onto its own subdomain, e.g. `app.lvh.me`
# instead of the apex `lvh.me` that auth/marketing keep). Links generated
# server-side into org-scoped app pages (billing portal returns, trial /
# dunning emails) must point here, not at FRONTEND_URL.
APP_FRONTEND_URL = env("KEEL_APP_FRONTEND_URL", default=None)
if APP_FRONTEND_URL is None:
    _frontend_parts = urlsplit(FRONTEND_URL)
    _frontend_host = _frontend_parts.hostname or ""
    if KEEL_APP_DOMAIN == "localhost" or _frontend_host.startswith("app."):
        APP_FRONTEND_URL = FRONTEND_URL
    else:
        _port = f":{_frontend_parts.port}" if _frontend_parts.port else ""
        APP_FRONTEND_URL = urlunsplit(
            (
                _frontend_parts.scheme,
                f"app.{_frontend_host}{_port}",
                _frontend_parts.path,
                _frontend_parts.query,
                _frontend_parts.fragment,
            )
        )
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/verify-email/{{key}}",
    "account_reset_password_from_key": f"{FRONTEND_URL}/reset-password/{{key}}",
    "socialaccount_login_error": f"{FRONTEND_URL}/login?error=provider",
    # Needed by allauth's enumeration-prevention path, not by any
    # redirect: signing up with an address that already has an account
    # sends *that* address a "you already have an account" mail, and
    # building it calls get_signup_url(). Without this key allauth raises
    # ImproperlyConfigured and the request 500s — so the one flow whose
    # entire purpose is to be indistinguishable from a fresh signup was
    # instead the only one that returned an error. Found on a live
    # deploy by signing up twice with the same address.
    "account_signup": f"{FRONTEND_URL}/signup",
    # Same path: that mail's body offers "reset your password" and builds
    # the link from this key.
    "account_reset_password": f"{FRONTEND_URL}/reset-password",
}
# `/invite/[token]` also appears in this settings-doc's PRD passage but is
# an organizations concept, not an allauth flow — it is not a
# HEADLESS_FRONTEND_URLS key because allauth never redirects there.

# keel.notifications.adapter routes verification/reset emails through
# the react-email templates.
ACCOUNT_ADAPTER = "keel.notifications.adapter.KeelAccountAdapter"

ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# Off by default in allauth. On here: clicking the emailed verification
# link is this app's only way to finish signup (there is no separate
# login step in between — apps/web/app/(auth)/verify-email/[key]/page.tsx
# redirects straight to /onboarding), so without this the link verifies
# the address but leaves the visitor unauthenticated on a page that
# already told them it worked.
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
# Off by default in allauth. On here: successfully resetting a password
# is proof of inbox access — the same proof `ACCOUNT_EMAIL_VERIFICATION`
# mandatory otherwise demands via the separate confirmation email — so a
# reset should land the user in the app, not bounce them into a second
# "verify your email" gate they have no way to complete without the
# session this response is about to discard.
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
ACCOUNT_LOGIN_METHODS = {"email"}
# "password2" (confirm-password) is a classic-form-only concept — the
# headless API always exposes a single "password" field on the wire
# (allauth.headless.account.inputs.SignupInput), so it is left out here
# rather than configured to no effect.
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

# Rate limits, read from allauth.account.app_settings.RATE_LIMITS' defaults
# (PRD §8: "configured, not left at defaults you have not
# read") and restated explicitly here rather than left implicit, so a
# reviewer sees the policy in this file instead of in the library source.
ACCOUNT_RATE_LIMITS = {
    "change_password": "5/m/user",
    "manage_email": "10/m/user",
    "reset_password": "20/m/ip,5/m/key",
    "reauthenticate": "10/m/user",
    "reset_password_from_key": "20/m/ip",
    "signup": "20/m/ip",
    "login": "30/m/ip",
    "login_failed": "10/m/ip,5/300s/key",
}

# The one configured social provider (PRD §8). Credentials
# come from settings, not the DB-backed SocialApp model, so there is
# nothing to seed via a data migration or the admin. Adding a second
# provider is exactly this: another top-level key with its own APPS
# entry and env vars — no code change.
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [
            {
                "client_id": env("GOOGLE_OAUTH_CLIENT_ID", default=""),
                "secret": env("GOOGLE_OAUTH_CLIENT_SECRET", default=""),
                "key": "",
            },
        ],
    },
}
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"  # the provider already verified it
SOCIALACCOUNT_STORE_TOKENS = False

# MFA (TOTP): app is only installed (see INSTALLED_APPS above) when
# KEEL_MFA_ENABLED is true. WebAuthn ships in allauth but is out of scope
# for this template, so it is left out of SUPPORTED_TYPES even when TOTP
# is switched on.
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]

USERSESSIONS_TRACK_ACTIVITY = True

# --- Structured JSON logging (keel/core/logging.py) --------------------
# Every line is JSON and carries the request id set by
# keel.core.middleware.RequestIDMiddleware.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "keel.core.logging.JSONFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# --- Organisations / permissions (PRD §4 "Tenancy and permissions") -------
# The membership-resolution seam keel/core/authz.py documents: keel.core
# cannot import keel.organizations, so OrgScopedResource resolves the
# organisation through this dotted path instead.
KEEL_ORGANIZATION_RESOLVER = "keel.organizations.resolvers.resolve_organization"

# Custom roles are a per-project feature flag, off by default (PRD §4,
# "Tenancy and permissions") — the Role model and roles.manage permission
# exist regardless, so turning this on is a settings change, not a
# migration.
KEEL_CUSTOM_ROLES_ENABLED = env.bool("KEEL_CUSTOM_ROLES_ENABLED", default=False)

# Credits are a per-project feature flag, off by default (PRD §4, "Credits
# — the metered-billing primitive") — the
# CreditLedgerEntry/CreditBalance models and keel.billing.credits exist
# regardless, so turning this on is a settings change, not a migration.
# With it off: no endpoints, no meter, no cost.
BILLING_CREDITS = env.bool("BILLING_CREDITS", default=False)

# Seat-based billing sync on invitation acceptance — the hook exists in
# organizations/services.py now, gated off until billing wires a real
# seat-sync implementation.
BILLING_SEAT_PRICING = env.bool("BILLING_SEAT_PRICING", default=False)

# Stripe is the source of truth for plans/prices (PRD §7, "Plans and
# prices are seeded from Stripe by a management command"); local Plan/
# Price rows are a cache. Blank in dev/test — sync_stripe_plans and the
# checkout/portal/webhook views raise ImproperlyConfigured if a call is
# actually attempted without a key, rather than silently no-op'ing.
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")

# Verifies POST /api/v1/stripe/webhook/'s signature (PRD §6 "Stripe
# webhook", invariant "Unsigned or wrongly-signed → 400, log, change
# nothing, no retry"). Blank in dev/test for the same reason as
# STRIPE_SECRET_KEY above — tests supply their own signed payloads via
# stripe.Webhook's own signing helper against a fixture secret.
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

# Sentry (PRD §4 Integration points). Blank
# DSN in dev/test — sentry_sdk.init() with dsn=None is a documented
# no-op, so this is unconditional (keel/core/sentry.py). Release is tied
# to the git SHA: Railway sets RAILWAY_GIT_COMMIT_SHA automatically; the
# generic GIT_SHA fallback covers self-host and CI.
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="development")
SENTRY_RELEASE = env("RAILWAY_GIT_COMMIT_SHA", default=env("GIT_SHA", default="dev"))

# PostHog (PRD §4 Integration points). Same
# treatment as Sentry above — blank key in dev/test, and the client
# (keel/core/posthog.py) is a documented no-op without one.
POSTHOG_PROJECT_API_KEY = env("POSTHOG_PROJECT_API_KEY", default="")
POSTHOG_HOST = env("POSTHOG_HOST", default="https://us.i.posthog.com")

# --- Security headers (PRD §3 NFR "Security") -------------------------------
# NOSNIFF and REFERRER_POLICY are Django's own defaults already (3.0+ and
# 3.1+ respectively) — explicit here so the header is a documented
# decision, not an implicit default someone could accidentally change by
# not knowing it was relying on one. HSTS is prod.py's job (only correct
# over HTTPS, which dev/test aren't).
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Django's own pages only (admin, the OpenAPI schema UI) — the app's CSP
# is Next.js's job (apps/web/next.config.ts), since that's the origin
# actually rendering untrusted-adjacent HTML. 'unsafe-inline' on
# style-src is Django admin's own requirement (its templates carry
# inline `style=` attributes); nothing here is looser than that.
SECURE_CSP = {
    "default-src": ["'self'"],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:"],
    "frame-ancestors": ["'none'"],
}
