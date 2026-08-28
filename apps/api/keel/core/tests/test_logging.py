import json
import logging

from keel.core.logging import JSONFormatter, get_request_id, request_id_var


def _record(message: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="keel.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formats_as_valid_json_with_expected_keys() -> None:
    formatter = JSONFormatter()

    output = formatter.format(_record("hello world"))
    parsed = json.loads(output)

    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "keel.test"
    assert "timestamp" in parsed


def test_includes_request_id_when_set_on_the_contextvar() -> None:
    formatter = JSONFormatter()
    token = request_id_var.set("req-123")
    try:
        output = formatter.format(_record("with request id"))
    finally:
        request_id_var.reset(token)

    parsed = json.loads(output)
    assert parsed["request_id"] == "req-123"


def test_request_id_is_null_when_unset() -> None:
    formatter = JSONFormatter()

    output = formatter.format(_record("no request id"))
    parsed = json.loads(output)

    assert parsed["request_id"] is None


def test_includes_exc_info_when_present() -> None:
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record("failed", exc_info=sys.exc_info())

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "ValueError" in parsed["exc_info"]
    assert "boom" in parsed["exc_info"]


def test_get_request_id_reads_the_contextvar() -> None:
    assert get_request_id() is None

    token = request_id_var.set("abc")
    try:
        assert get_request_id() == "abc"
    finally:
        request_id_var.reset(token)


# --- Redaction -----------------------------------------------------------


def test_no_extra_key_when_nothing_was_attached() -> None:
    formatter = JSONFormatter()

    parsed = json.loads(formatter.format(_record("plain")))

    assert "extra" not in parsed


def test_redacts_every_named_secret_category() -> None:
    """Matching is substring-on-key, deliberately over-inclusive
    (keel.core.redaction's module docstring) — a container key that
    itself names a secret category (``cookies``) is redacted wholesale
    rather than recursed into, same as a scalar secret value would be."""
    formatter = JSONFormatter()
    record = _record(
        "request failed",
        headers={
            "Authorization": "Bearer abc123",
            "X-CSRFToken": "csrf-value",
            "Content-Type": "application/json",
        },
        cookies={"sessionid": "sess-abc", "csrftoken": "csrf-abc"},
        oauth_access_token="oauth-access-value",
        oauth_refresh_token="oauth-refresh-value",
        api_key="sk_live_abcdef",
        stripe_signature="t=123,v1=deadbeef",
        password="hunter2",
        user_email="dev@example.com",
    )

    parsed = json.loads(formatter.format(record))
    extra = parsed["extra"]

    assert extra["headers"]["Authorization"] == "[REDACTED]"
    assert extra["headers"]["X-CSRFToken"] == "[REDACTED]"
    assert extra["headers"]["Content-Type"] == "application/json"
    assert extra["cookies"] == "[REDACTED]"
    assert extra["oauth_access_token"] == "[REDACTED]"
    assert extra["oauth_refresh_token"] == "[REDACTED]"
    assert extra["api_key"] == "[REDACTED]"
    assert extra["stripe_signature"] == "[REDACTED]"
    assert extra["password"] == "[REDACTED]"
    # A field that doesn't name a secret passes through unredacted — the
    # mechanism must not blanket-redact everything.
    assert extra["user_email"] == "dev@example.com"


def test_redacts_inside_a_list_of_dicts() -> None:
    formatter = JSONFormatter()
    record = _record("batch", items=[{"token": "abc"}, {"note": "fine"}])

    parsed = json.loads(formatter.format(record))

    assert parsed["extra"]["items"] == [{"token": "[REDACTED]"}, {"note": "fine"}]


def test_extra_survives_a_non_json_serializable_value() -> None:
    """``default=str`` — a log call attaching an arbitrary object (a
    model instance, a UUID) must not crash formatting."""
    formatter = JSONFormatter()
    record = _record("weird value", request_id=object())

    output = formatter.format(record)

    assert json.loads(output)["extra"]["request_id"]
