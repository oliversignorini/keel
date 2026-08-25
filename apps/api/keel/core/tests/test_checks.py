"""PRD §10, first named risk: a SESSION_COOKIE_DOMAIN that is not a parent
of the app's registrable domain must fail `manage.py check`, not silently
break login in production."""

from django.test import override_settings

from keel.core.checks import check_session_cookie_domain


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
