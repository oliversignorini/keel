"""``keel.core.redaction`` — the shared denylist behind both
``keel.core.logging.JSONFormatter`` and ``keel.core.sentry``'s
``before_send`` scrubber (docs/plans/phase-16.md 16.B)."""

from keel.core.redaction import is_sensitive_key, redact_mapping


def test_is_sensitive_key_matches_every_named_category() -> None:
    for key in (
        "Authorization",
        "authorization",
        "Cookie",
        "Set-Cookie",
        "X-CSRFToken",
        "csrf_token",
        "sessionid",
        "session_key",
        "access_token",
        "refresh_token",
        "api_key",
        "apiKey",
        "client_secret",
        "Stripe-Signature",
        "password",
        "passwd",
    ):
        assert is_sensitive_key(key), key


def test_is_sensitive_key_leaves_ordinary_fields_alone() -> None:
    for key in ("email", "organization_id", "status", "Content-Type", "user_agent"):
        assert not is_sensitive_key(key), key


def test_redact_mapping_leaves_non_mapping_scalars_untouched() -> None:
    assert redact_mapping("plain string") == "plain string"
    assert redact_mapping(42) == 42
    assert redact_mapping(None) is None


def test_redact_mapping_walks_nested_lists_and_tuples() -> None:
    data = {"items": ("a", {"password": "hunter2"})}

    result = redact_mapping(data)

    assert result == {"items": ["a", {"password": "[REDACTED]"}]}


def test_redact_mapping_redacts_a_container_whose_own_key_names_a_secret() -> None:
    """Deliberately over-inclusive (module docstring): a key like
    ``tokens`` matches the ``token`` substring and is redacted wholesale,
    not recursed into — the safer failure mode."""
    data = {"tokens": {"access": "abc"}}

    assert redact_mapping(data) == {"tokens": "[REDACTED]"}


def test_redact_mapping_does_not_mutate_its_input() -> None:
    original = {"password": "hunter2"}

    redact_mapping(original)

    assert original == {"password": "hunter2"}
