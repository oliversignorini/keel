"""Startup check for the cookie-domain misconfiguration named as the PRD's
first risk (§10): a ``SESSION_COOKIE_DOMAIN`` that is not a parent of the
app's registrable domain means the session cookie is never sent back to the
frontend, and login fails silently — nothing raises, nothing 500s, the
browser just never has a cookie. This check turns that into a loud failure
on ``manage.py check`` (and therefore on every deploy that runs it), rather
than a bug report about "login doesn't work" weeks later.
"""

from django.conf import settings
from django.core.checks import Error, register


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
