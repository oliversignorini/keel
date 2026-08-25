"""Base settings, shared by every environment. Reads configuration from env.

Env-config library: django-environ. Chosen over python-decouple because it
also parses DATABASE_URL / REDIS_URL / CACHE_URL into the dict shapes
Django's DATABASES/CACHES settings expect (env.db(), env.cache()), which
removes a class of hand-rolled URL-parsing bugs that a plain decouple-style
config() call would otherwise need helpers for.
"""

import sys
from pathlib import Path

import django
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# --- Version floor -----------------------------------------------------
# A project that needs an older Django or Python is a fork, not a
# configuration (PRD §8, Phase 0).
if sys.version_info < (3, 12):  # noqa: UP036 - a floor assertion, not dead code
    raise RuntimeError("Keel requires Python 3.12 or newer.")
if django.VERSION < (6, 0):
    raise RuntimeError("Keel requires Django 6.0 or newer.")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# --- MFA scaffold flag (PRD §8 Phase 2, A.1) -------------------------------
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
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    # allauth headless (PRD §4 "Auth architecture", §8 Phase 2)
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.usersessions",
    # Keel apps — empty in Phase 0, registered so Phase 1's baseline
    # migration has somewhere to land. No models here yet.
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
    "keel.core.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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

# --- Cookies, CORS, CSRF (PRD §4 "Auth architecture", §10 first named risk) -
# Session transport is an HttpOnly cookie, not a JWT (PRD §4). The cookie's
# Domain must be the *registrable* domain — `.acme.com` — so it is shared
# between `acme.com` (Next.js) and `api.acme.com` (Django). KEEL_APP_DOMAIN
# is that registrable domain; SESSION_COOKIE_DOMAIN is derived from it
# rather than duplicated, so the two cannot drift apart in an env file.
# Local dev serves both sides off "localhost" with no port-spanning cookie
# issue, so KEEL_APP_DOMAIN defaults there and SESSION_COOKIE_DOMAIN is left
# unset (host-only cookie) unless a real domain is configured — Chrome
# rejects `Domain=localhost` cookies set with a leading dot.
KEEL_APP_DOMAIN = env("KEEL_APP_DOMAIN", default="localhost")
SESSION_COOKIE_DOMAIN = env(
    "DJANGO_SESSION_COOKIE_DOMAIN",
    default=None if KEEL_APP_DOMAIN == "localhost" else f".{KEEL_APP_DOMAIN}",
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
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])
CORS_ALLOW_CREDENTIALS = True

# --- Email (Mailpit in dev, see infra/compose.dev.yml) ---------------------
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@keel.local")

# --- Encryption (keel/core/crypto.py) ---------------------------------
# Backs Connection.access_token / refresh_token. Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
KEEL_ENCRYPTION_KEY = env("KEEL_ENCRYPTION_KEY", default="")

# --- DRF ---------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Deny by default (PRD §4, task 1.12) — a viewset that forgets to
    # declare permissions is unreachable rather than open.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "keel.core.pagination.CursorPagination",
    "EXCEPTION_HANDLER": "keel.core.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Keel API",
    "DESCRIPTION": "Keel — Django + Next.js SaaS template.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Matches allauth headless's own spec version (3.0.3) so
    # scripts/merge_openapi.py (A.3) merges two documents in the same
    # OpenAPI dialect rather than mixing 3.0 and 3.1 JSON Schema variants.
    "OAS_VERSION": "3.0.3",
}

# --- allauth headless (PRD §4 "Auth architecture", §8 Phase 2 A.1) ---------
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
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/verify-email/{{key}}",
    "account_reset_password_from_key": f"{FRONTEND_URL}/reset-password/{{key}}",
    "socialaccount_login_error": f"{FRONTEND_URL}/login?error=provider",
}
# `/invite/[token]` also appears in this settings-doc's PRD passage but is
# an organizations (Phase 3) concept, not an allauth flow — it is not a
# HEADLESS_FRONTEND_URLS key because allauth never redirects there.

ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None

# Rate limits, read from allauth.account.app_settings.RATE_LIMITS' defaults
# (PRD §8 Phase 2 A.1: "configured, not left at defaults you have not
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

# The one configured social provider (PRD §8 Phase 2 A.1). Credentials
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
# KEEL_MFA_ENABLED is true. WebAuthn ships in allauth but is out of Phase 2
# scope per the plan, so it is left out of SUPPORTED_TYPES even when TOTP
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
