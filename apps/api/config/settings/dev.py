from .base import *  # noqa: F403

DEBUG = True

# base.py computes SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE as
# `not DEBUG` *before* this module ever runs — `DEBUG` there is
# `env("DJANGO_DEBUG")`, defaulting to False, not this module's
# hardcoded `DEBUG = True` above. A dev checkout that forgets to set
# DJANGO_DEBUG=true in its .env therefore gets Secure cookies while
# genuinely running in DEBUG mode: the browser silently drops both
# cookies over plain http://lvh.me, and login fails with no cookie ever
# set and no error anywhere (keel.core.checks.check_secure_cookies_match_debug
# turns this into a loud `manage.py check` failure rather than a silent
# one). Set explicitly here rather than relying on the env var alignment.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
