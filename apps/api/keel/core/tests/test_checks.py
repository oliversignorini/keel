"""PRD §10, first named risk: a SESSION_COOKIE_DOMAIN that is not a parent
of the app's registrable domain must fail `manage.py check`, not silently
break login in production."""

from django.test import override_settings

from keel.core.checks import (
    check_csrf_trusted_origins_cover_app_domain,
    check_secure_cookies_match_debug,
    check_session_cookie_domain,
)


def test_passes_when_cookie_domain_is_unset() -> None:
    with override_settings(SESSION_COOKIE_DOMAIN=None, KEEL_APP_DOMAIN="localhost"):
        assert check_session_cookie_domain(None) == []


def test_passes_when_cookie_domain_equals_app_domain() -> None:
    with override_settings(SESSION_COOKIE_DOMAIN=".acme.com", KEEL_APP_DOMAIN="acme.com"):
        assert check_session_cookie_domain(None) == []


def test_passes_when_app_domain_is_a_subdomain_of_the_cookie_domain() -> None:
    with override_settings(SESSION_COOKIE_DOMAIN=".acme.com", KEEL_APP_DOMAIN="api.acme.com"):
        assert check_session_cookie_domain(None) == []


def test_fails_when_cookie_domain_lacks_a_leading_dot() -> None:
    with override_settings(SESSION_COOKIE_DOMAIN="acme.com", KEEL_APP_DOMAIN="acme.com"):
        errors = check_session_cookie_domain(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E001"


def test_fails_when_cookie_domain_is_not_a_parent_of_the_app_domain() -> None:
    with override_settings(SESSION_COOKIE_DOMAIN=".notacme.com", KEEL_APP_DOMAIN="acme.com"):
        errors = check_session_cookie_domain(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E002"


def test_fails_when_app_domain_is_only_a_suffix_match_not_a_subdomain() -> None:
    """ "notacme.com" ends with "acme.com" as a raw string, but is not a
    subdomain of it — the check must compare domain labels, not do a bare
    string suffix match."""
    with override_settings(SESSION_COOKIE_DOMAIN=".acme.com", KEEL_APP_DOMAIN="notacme.com"):
        errors = check_session_cookie_domain(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E002"


def test_secure_cookies_pass_when_debug_is_false() -> None:
    with override_settings(DEBUG=False, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True):
        assert check_secure_cookies_match_debug(None) == []


def test_insecure_cookies_pass_when_debug_is_true() -> None:
    with override_settings(DEBUG=True, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False):
        assert check_secure_cookies_match_debug(None) == []


def test_fails_when_debug_is_true_and_session_cookie_is_secure() -> None:
    """The Phase 11 DEBUG-ordering trap: config/settings/dev.py sets
    DEBUG = True after importing base.py, which already computed
    SESSION_COOKIE_SECURE from the environment's DJANGO_DEBUG (default
    False) — a checkout that never set that env var gets Secure cookies
    while genuinely running in DEBUG mode."""
    with override_settings(DEBUG=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=False):
        errors = check_secure_cookies_match_debug(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E003"


def test_fails_when_debug_is_true_and_csrf_cookie_is_secure() -> None:
    with override_settings(DEBUG=True, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=True):
        errors = check_secure_cookies_match_debug(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E003"


def test_csrf_trusted_origins_pass_when_app_domain_is_covered() -> None:
    with override_settings(
        KEEL_APP_DOMAIN="app.acme.com",
        CSRF_TRUSTED_ORIGINS=["https://app.acme.com", "https://acme.com"],
    ):
        assert check_csrf_trusted_origins_cover_app_domain(None) == []


def test_fails_when_no_trusted_origin_matches_the_app_domain() -> None:
    """Phase 11: the BFF forwards the browser's Origin/Referer to Django
    unchanged, so a CSRF_TRUSTED_ORIGINS that doesn't cover KEEL_APP_DOMAIN
    means every unsafe request the BFF forwards gets a CSRF 403 under
    HTTPS — the one environment where the check actually runs."""
    with override_settings(
        KEEL_APP_DOMAIN="app.acme.com",
        CSRF_TRUSTED_ORIGINS=["https://notacme.com"],
    ):
        errors = check_csrf_trusted_origins_cover_app_domain(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E004"
