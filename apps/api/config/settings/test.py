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
