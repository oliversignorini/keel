"""Test settings.

Uses a real Postgres, not sqlite: tenant-isolation and ledger tests in
later phases depend on Postgres semantics (row locking, JSONB, etc.), and
switching test backends mid-build is a trap. Django creates and tears
down a `test_<name>` database automatically against the same server.
"""

from .base import *  # noqa: F403

DEBUG = False

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# allauth's rate limiting (base.py's ACCOUNT_RATE_LIMITS) is keyed in the
# real Redis cache, which persists across test runs — a "confirm_email"
# cooldown hit by one test's email address silently suppresses the next
# test's confirmation email for the same address, and the failure looks
# like a wiring bug rather than shared external state. Rate-limit
# *behavior* is allauth's own, already-tested code; disabling it here
# keeps this project's tests deterministic regardless of run history.
ACCOUNT_RATE_LIMITS = False  # type: ignore[assignment]
