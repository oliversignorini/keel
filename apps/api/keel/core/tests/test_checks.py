"""PRD §10, first named risk: a SESSION_COOKIE_DOMAIN that is not a parent
of the app's registrable domain must fail `manage.py check`, not silently
break login in production."""

from django.test import override_settings

from keel.core.checks import (
    check_allowed_hosts_not_wildcard,
    check_cors_not_wildcard,
    check_csrf_trusted_origins_cover_app_domain,
    check_csrf_trusted_origins_not_wildcard,
    check_secret_key_not_default,
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
    """The DEBUG-ordering trap: config/settings/dev.py sets
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
    """The BFF forwards the browser's Origin/Referer to Django
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


# --- Production-only checks -------------------------------------------------
# `KEEL_ENFORCE_PRODUCTION_CHECKS` is only ever True under
# config/settings/prod.py — every test below sets it explicitly rather than
# relying on the settings module the test suite happens to run under.


def test_secret_key_check_is_a_no_op_when_production_checks_are_not_enforced() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=False, SECRET_KEY="insecure-dev-key-change-me"
    ):
        assert check_secret_key_not_default(None) == []


def test_secret_key_check_passes_with_a_long_random_key() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True,
        SECRET_KEY="a" * 10 + "b" * 10 + "c" * 10 + "d" * 10 + "e" * 10,
    ):
        assert check_secret_key_not_default(None) == []


def test_secret_key_check_fails_on_the_base_py_default() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True, SECRET_KEY="insecure-dev-key-change-me"
    ):
        errors = check_secret_key_not_default(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E005"


def test_secret_key_check_fails_on_a_short_key_even_if_not_the_literal_default() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=True, SECRET_KEY="short-but-different"):
        errors = check_secret_key_not_default(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E005"


def test_secret_key_check_fails_on_the_django_insecure_prefix() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True,
        SECRET_KEY="django-insecure-" + "x" * 40,
    ):
        errors = check_secret_key_not_default(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E005"


def test_allowed_hosts_check_is_a_no_op_when_production_checks_are_not_enforced() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=False, ALLOWED_HOSTS=["*"]):
        assert check_allowed_hosts_not_wildcard(None) == []


def test_allowed_hosts_check_passes_with_real_hosts() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True, ALLOWED_HOSTS=["app.acme.com", "api.acme.com"]
    ):
        assert check_allowed_hosts_not_wildcard(None) == []


def test_allowed_hosts_check_fails_on_wildcard() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=True, ALLOWED_HOSTS=["*"]):
        errors = check_allowed_hosts_not_wildcard(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E006"


def test_allowed_hosts_check_fails_when_empty() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=True, ALLOWED_HOSTS=[]):
        errors = check_allowed_hosts_not_wildcard(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E006"


def test_csrf_origins_wildcard_check_is_a_no_op_when_not_enforced() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=False, CSRF_TRUSTED_ORIGINS=[]):
        assert check_csrf_trusted_origins_not_wildcard(None) == []


def test_csrf_trusted_origins_wildcard_check_passes_with_real_origins() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True, CSRF_TRUSTED_ORIGINS=["https://app.acme.com"]
    ):
        assert check_csrf_trusted_origins_not_wildcard(None) == []


def test_csrf_trusted_origins_wildcard_check_fails_on_wildcard() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True, CSRF_TRUSTED_ORIGINS=["https://*.acme.com"]
    ):
        errors = check_csrf_trusted_origins_not_wildcard(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E007"


def test_csrf_trusted_origins_wildcard_check_fails_when_empty() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=True, CSRF_TRUSTED_ORIGINS=[]):
        errors = check_csrf_trusted_origins_not_wildcard(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E007"


def test_cors_check_is_a_no_op_when_not_enforced() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=False, CORS_ALLOW_ALL_ORIGINS=True):
        assert check_cors_not_wildcard(None) == []


def test_cors_check_passes_with_an_empty_allowlist() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True,
        CORS_ALLOWED_ORIGINS=[],
        CORS_ALLOW_ALL_ORIGINS=False,
    ):
        assert check_cors_not_wildcard(None) == []


def test_cors_check_fails_when_allow_all_origins_is_true() -> None:
    with override_settings(KEEL_ENFORCE_PRODUCTION_CHECKS=True, CORS_ALLOW_ALL_ORIGINS=True):
        errors = check_cors_not_wildcard(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E008"


def test_cors_check_fails_when_wildcard_is_in_the_allowed_origins_list() -> None:
    with override_settings(
        KEEL_ENFORCE_PRODUCTION_CHECKS=True,
        CORS_ALLOWED_ORIGINS=["*"],
        CORS_ALLOW_ALL_ORIGINS=False,
    ):
        errors = check_cors_not_wildcard(None)

    assert len(errors) == 1
    assert errors[0].id == "keel.core.E008"
