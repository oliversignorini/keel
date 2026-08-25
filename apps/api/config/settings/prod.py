from .base import *  # noqa: F403
from .base import env

DEBUG = False

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = "DENY"

# Resend (docs/plans/phase-5.md 5.5) — see
# keel.notifications.resend_backend for why this is a backend rather
# than a bespoke send path.
EMAIL_BACKEND = "keel.notifications.resend_backend.ResendEmailBackend"
