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
