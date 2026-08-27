from .base import *  # noqa: F403
from .base import DATABASES, MIDDLEWARE, env

DEBUG = False

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = "DENY"

# Railway's (and every other reverse-proxy PaaS's) edge terminates TLS and
# forwards the original scheme via X-Forwarded-Proto — without this,
# Django sees every request as plain HTTP behind the proxy, which makes
# SECURE_SSL_REDIRECT above loop forever (redirect to https://, proxy
# forwards as http://, redirect again) and reports every request as
# insecure to SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE. Safe only because
# Railway's proxy sets this header itself and strips/overwrites any
# client-supplied one — see docs/deploy-railway.md's production checklist
# for the one thing this hasn't been confirmed against: a real Railway
# deploy inspecting the header Railway's edge actually sends.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Resend (docs/plans/phase-5.md 5.5) — see
# keel.notifications.resend_backend for why this is a backend rather
# than a bespoke send path.
EMAIL_BACKEND = "keel.notifications.resend_backend.ResendEmailBackend"

# --- Database connection pooling (docs/deploy-railway.md "Pooling") -------
# Railway Postgres has no pooler in front of it — a long-lived
# CONN_MAX_AGE is safe and cuts per-request connection-setup overhead.
# Neon's pooled endpoint (the one its dashboard hands out by default,
# hostname containing "-pooler") is PgBouncer in transaction mode, which
# reclaims the underlying connection at the end of every transaction —
# a Django-side persistent connection on top of that pools nothing and
# just holds a slot in Neon's own limited pooler, so CONN_MAX_AGE must
# stay 0 there. One env var covers both: point it at Railway's number
# when deploying to Railway Postgres, leave it at the 0 default for Neon.
# Transaction-mode pooling also breaks SQL-level server-side cursors
# (session state does not survive across pooled transactions), so
# DISABLE_SERVER_SIDE_CURSORS follows the same flag.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DJANGO_DB_CONN_MAX_AGE", default=0)
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = env.bool(
    "DJANGO_DB_DISABLE_SERVER_SIDE_CURSORS", default=False
)

# --- Static files (Django admin CSS/JS) ------------------------------------
# DEBUG=True serves STATIC_ROOT's contents directly in dev; prod needs
# something to answer /static/*. WhiteNoise serves the collectstatic
# output (apps/api/Dockerfile's build-time `collectstatic` step) straight
# from the app container rather than adding a CDN/object-storage step for
# what is, today, only the Django admin's own assets.
MIDDLEWARE = [*MIDDLEWARE[:1], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]
STORAGES = {
    # Unchanged from Django's own default — nothing in this codebase uses
    # django.core.files.storage.default_storage (file uploads go through
    # keel.files.r2_client to R2/MinIO instead), but STORAGES is an
    # all-or-nothing setting: defining the dict at all means both keys
    # must be present, or FileField's default storage silently disappears.
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
