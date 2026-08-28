"""Test settings.

Uses a real Postgres, not sqlite: tenant-isolation and ledger tests
depend on Postgres semantics (row locking, JSONB, etc.), and switching
test backends mid-build is a trap. Django creates and tears
down a `test_<name>` database automatically against the same server.
"""

from .base import *  # noqa: F403

DEBUG = False

# Hardcoded, not derived from DEBUG or read from the environment — unlike
# prod.py (which hardcodes the same values) base.py's
# SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)
# resolves at base.py import time, using *base's own* DEBUG (from
# DJANGO_DEBUG / a developer's untracked .env), before this module's
# `DEBUG = False` above ever runs — so it does not retroactively flip.
# A developer's local .env (DJANGO_DEBUG=true for their own dev server,
# entirely reasonable there) would otherwise silently flip this suite's
# cookie-security assertions depending on who ran it and where, which
# makes the suite non-hermetic: same code, different result by machine.
# Explicit values here make the test suite's result depend only on the
# code, never on ambient environment or an untracked .env.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Empty, not the MinIO default from base.py:
# keel.files.storage.S3CompatibleStorage omits ``endpoint_url`` entirely
# when this is blank, which is what lets ``moto``'s mocked S3 intercept
# these calls (see keel/files/tests/test_uploads.py) — a custom
# endpoint_url bypasses moto's interception, since it only recognises
# real AWS-shaped hosts.
R2_ENDPOINT_URL = ""
R2_BUCKET = "keel-test"
STORAGES["files"]["OPTIONS"]["endpoint_url"] = R2_ENDPOINT_URL  # noqa: F405
STORAGES["files"]["OPTIONS"]["bucket"] = R2_BUCKET  # noqa: F405

# allauth's rate limiting (base.py's ACCOUNT_RATE_LIMITS) is keyed in the
# real Redis cache, which persists across test runs — a "confirm_email"
# cooldown hit by one test's email address silently suppresses the next
# test's confirmation email for the same address, and the failure looks
# like a wiring bug rather than shared external state. Rate-limit
# *behavior* is allauth's own, already-tested code; disabling it here
# keeps this project's tests deterministic regardless of run history.
ACCOUNT_RATE_LIMITS = False  # type: ignore[assignment]

# Same reasoning as ACCOUNT_RATE_LIMITS above, for the general API
# throttle: keel.core.throttle's
# counters live in the same real Redis cache, keyed by client ident/user
# id, and persist across the whole test run — hundreds of tests hitting
# the same endpoints would otherwise trip an unrelated test's rate limit
# purely from run history. `None` short-circuits both throttles' `check()`.
# tests/test_rate_limiting.py constructs throttle instances with an
# explicit `rate=` (and clears the cache first) to test the mechanism
# itself, bypassing this.
KEEL_API_THROTTLE_USER_RATE = None
KEEL_API_THROTTLE_ANON_RATE = None
