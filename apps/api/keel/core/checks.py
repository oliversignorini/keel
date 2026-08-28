"""Startup check for the cookie-domain misconfiguration named as the PRD's
first risk (§10): a ``SESSION_COOKIE_DOMAIN`` that is not a parent of the
app's registrable domain means the session cookie is never sent back to the
frontend, and login fails silently — nothing raises, nothing 500s, the
browser just never has a cookie. This check turns that into a loud failure
on ``manage.py check`` (and therefore on every deploy that runs it), rather
than a bug report about "login doesn't work" weeks later.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, register
from django.core.checks.security.base import (
    SECRET_KEY_INSECURE_PREFIX,
    SECRET_KEY_MIN_LENGTH,
    SECRET_KEY_MIN_UNIQUE_CHARACTERS,
)


@register()
def check_session_cookie_domain(app_configs: object, **kwargs: object) -> list[Error]:
    cookie_domain = settings.SESSION_COOKIE_DOMAIN
    if cookie_domain is None:
        # Host-only cookie: valid for exactly one host, never shared across
        # a subdomain split. Correct for single-host/local setups; PRD §4's
        # constraint only bites once the app and API live on different
        # subdomains, which is what the checks below actually guard.
        return []

    if not cookie_domain.startswith("."):
        return [
            Error(
                f"SESSION_COOKIE_DOMAIN={cookie_domain!r} does not start with '.'.",
                hint=(
                    "A registrable-domain cookie must be dot-prefixed, e.g. "
                    "'.acme.com', so it is shared between acme.com and "
                    "api.acme.com (PRD sec. 4 'Auth architecture')."
                ),
                id="keel.core.E001",
            )
        ]

    registrable_domain = cookie_domain[1:]
    app_domain = settings.KEEL_APP_DOMAIN
    is_same_or_subdomain = app_domain == registrable_domain or app_domain.endswith(
        f".{registrable_domain}"
    )
    if not is_same_or_subdomain:
        return [
            Error(
                f"SESSION_COOKIE_DOMAIN={cookie_domain!r} is not a parent of "
                f"KEEL_APP_DOMAIN={app_domain!r}.",
                hint=(
                    "The browser will not send the session cookie back to the app "
                    "domain, and login fails silently (PRD sec. 10, first named risk). "
                    "Set DJANGO_SESSION_COOKIE_DOMAIN to '.' + the registrable "
                    "domain shared by the app and API, e.g. app domain "
                    "'api.acme.com' needs cookie domain '.acme.com'."
                ),
                id="keel.core.E002",
            )
        ]

    return []


@register()
def check_secure_cookies_match_debug(app_configs: object, **kwargs: object) -> list[Error]:
    """The DEBUG-ordering trap: ``config/settings/base.py`` computes
    ``SESSION_COOKIE_SECURE`` / ``CSRF_COOKIE_SECURE`` as ``not DEBUG`` at
    import time, where ``DEBUG`` is ``env("DJANGO_DEBUG")`` — a settings
    module that overrides ``DEBUG`` afterwards (``config/settings/dev.py``)
    does not retroactively change that computation. A checkout that never
    set ``DJANGO_DEBUG=true`` in its environment ends up genuinely running
    in ``DEBUG`` mode with ``Secure`` cookies, which the browser silently
    drops over plain HTTP — login then fails with no cookie ever set and
    no error anywhere. This turns that into a loud, immediate failure."""
    if settings.DEBUG and (settings.SESSION_COOKIE_SECURE or settings.CSRF_COOKIE_SECURE):
        return [
            Error(
                "SESSION_COOKIE_SECURE or CSRF_COOKIE_SECURE is True while DEBUG is True.",
                hint=(
                    "A Secure cookie is dropped by the browser over plain HTTP, which is "
                    "how the dev/e2e server runs. Set DJANGO_DEBUG=true in the environment "
                    "(not just a settings module's own DEBUG override) so "
                    "config/settings/base.py computes SESSION_COOKIE_SECURE (and, from it, "
                    "CSRF_COOKIE_SECURE) as False, or set "
                    "DJANGO_SESSION_COOKIE_SECURE=false explicitly."
                ),
                id="keel.core.E003",
            )
        ]

    return []


@register()
def check_csrf_trusted_origins_cover_app_domain(
    app_configs: object, **kwargs: object
) -> list[Error]:
    """docs/adr/0002-auth-bff-shape.md: the BFF proxy forwards
    the browser's original ``Origin``/``Referer`` headers unchanged, and
    Django's CSRF middleware validates those against
    ``CSRF_TRUSTED_ORIGINS`` (only when the request is secure, but a
    misconfiguration here is real regardless of scheme — it just fails
    silently over plain HTTP in dev, per ``CsrfViewMiddleware``'s own
    referer-check gating). ``KEEL_APP_DOMAIN`` not being covered by any
    trusted origin means every unsafe request the BFF forwards — which
    is every login, every signup, every mutation — gets a CSRF 403 in
    any deployment that terminates TLS, the one environment where the
    check actually runs."""
    app_domain = settings.KEEL_APP_DOMAIN
    trusted_hosts = {urlparse(origin).hostname for origin in settings.CSRF_TRUSTED_ORIGINS}
    if app_domain not in trusted_hosts:
        return [
            Error(
                f"KEEL_APP_DOMAIN={app_domain!r} has no matching entry in "
                f"CSRF_TRUSTED_ORIGINS={sorted(settings.CSRF_TRUSTED_ORIGINS)!r}.",
                hint=(
                    "The Next.js BFF forwards the browser's own Origin/Referer to "
                    "Django unchanged, and CsrfViewMiddleware validates it against "
                    "CSRF_TRUSTED_ORIGINS on every unsafe request under HTTPS. Add "
                    "the app's real scheme+host (e.g. 'https://app.acme.com') to "
                    "DJANGO_CSRF_TRUSTED_ORIGINS."
                ),
                id="keel.core.E004",
            )
        ]

    return []


def _production_checks_enforced() -> bool:
    """``config/settings/prod.py`` is the only settings module that sets
    this — see its comment for why an explicit flag, not DEBUG or the
    settings module name, gates the checks below."""
    return bool(getattr(settings, "KEEL_ENFORCE_PRODUCTION_CHECKS", False))


@register()
def check_secret_key_not_default(app_configs: object, **kwargs: object) -> list[Error]:
    """Production must fail to start on the default SECRET_KEY. Django's
    own ``security.W009`` already flags a
    weak key (same weakness test, reused here via the same constants it
    uses) but only as a warning that ``manage.py check --deploy`` prints
    and moves on from. This is the same test as an ``Error``, so a
    deployment that never set ``DJANGO_SECRET_KEY`` (``base.py``'s
    ``insecure-dev-key-change-me`` default) fails to boot instead of
    silently running with a key an attacker can guess."""
    if not _production_checks_enforced():
        return []

    secret_key = settings.SECRET_KEY
    if (
        len(set(secret_key)) < SECRET_KEY_MIN_UNIQUE_CHARACTERS
        or len(secret_key) < SECRET_KEY_MIN_LENGTH
        or secret_key.startswith(SECRET_KEY_INSECURE_PREFIX)
    ):
        return [
            Error(
                "SECRET_KEY is missing, too short, too predictable, or still the "
                "insecure development default.",
                hint=(
                    "Set DJANGO_SECRET_KEY to a long, random value before deploying "
                    "(security.W009's own criterion, enforced here as a hard failure "
                    "rather than a warning). Generate one with "
                    '`python -c "from django.core.management.utils import '
                    'get_random_secret_key; print(get_random_secret_key())"`.'
                ),
                id="keel.core.E005",
            )
        ]

    return []


@register()
def check_allowed_hosts_not_wildcard(app_configs: object, **kwargs: object) -> list[Error]:
    """Validate that ALLOWED_HOSTS is set and not a wildcard in
    production. Django itself only warns
    (``security.W020``, not enabled by ``--deploy``) when ``DEBUG`` is
    also ``True`` — which prod.py never is — so a wildcard host here has
    no other gate at all."""
    if not _production_checks_enforced():
        return []

    if not settings.ALLOWED_HOSTS or "*" in settings.ALLOWED_HOSTS:
        return [
            Error(
                f"ALLOWED_HOSTS={settings.ALLOWED_HOSTS!r} is empty or contains a wildcard.",
                hint=(
                    "A wildcard or empty ALLOWED_HOSTS accepts the Host header from "
                    "any caller, which defeats Django's own Host-header validation "
                    "(cache-poisoning / password-reset-link-poisoning surface). Set "
                    "DJANGO_ALLOWED_HOSTS to the real, comma-separated list of hosts "
                    "this deployment answers for."
                ),
                id="keel.core.E006",
            )
        ]

    return []


@register()
def check_csrf_trusted_origins_not_wildcard(app_configs: object, **kwargs: object) -> list[Error]:
    """CSRF_TRUSTED_ORIGINS must be set and not a wildcard in
    production — the counterpart to
    ``check_allowed_hosts_not_wildcard`` above for the header Django's
    CSRF middleware actually validates unsafe requests against."""
    if not _production_checks_enforced():
        return []

    origins = settings.CSRF_TRUSTED_ORIGINS
    if not origins or any("*" in origin for origin in origins):
        return [
            Error(
                f"CSRF_TRUSTED_ORIGINS={origins!r} is empty or contains a wildcard.",
                hint=(
                    "A wildcard origin defeats CsrfViewMiddleware's Origin/Referer "
                    "check. Set DJANGO_CSRF_TRUSTED_ORIGINS to the real scheme+host "
                    "origins this deployment's frontend is served from (e.g. "
                    "'https://app.acme.com')."
                ),
                id="keel.core.E007",
            )
        ]

    return []


@register()
def check_cors_not_wildcard(app_configs: object, **kwargs: object) -> list[Error]:
    """CORS origins must be set and not a wildcard in production.
    ``CORS_ALLOW_CREDENTIALS = True`` (base.py) already
    makes django-cors-headers itself refuse to reflect ``*`` at request
    time, but that failure is a same-request 4xx a caller discovers by
    trying, not a deploy-time signal that the configuration is wrong."""
    if not _production_checks_enforced():
        return []

    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False) or "*" in settings.CORS_ALLOWED_ORIGINS:
        return [
            Error(
                "CORS_ALLOW_ALL_ORIGINS is True, or '*' is in CORS_ALLOWED_ORIGINS.",
                hint=(
                    "docs/adr/0002-auth-bff-shape.md: no browser fetch()/XHR should "
                    "reach Django directly with credentials in production — "
                    "DJANGO_CORS_ALLOWED_ORIGINS should stay unset (empty) unless a "
                    "deployment has a real, named direct-browser caller, in which "
                    "case list its exact origin(s), never a wildcard."
                ),
                id="keel.core.E008",
            )
        ]

    return []
