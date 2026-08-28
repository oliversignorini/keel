"""Structured JSON logging (PRD §4, task 1.12): every line is a JSON
object, and every line carries the request id set by
``keel.core.middleware.RequestIDMiddleware`` — the seam between the two
is this module's ``request_id_var`` contextvar.

Any structured data a call site attaches via ``logger.info(msg,
extra={...})`` is redacted through ``keel.core.redaction.redact_mapping``
before serialisation — a log line is exactly
as much of a leak surface as a Sentry event, and both go through the same
denylist so "what counts as a secret" can't drift between them."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from keel.core.redaction import redact_mapping

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()


# Every attribute a bare LogRecord carries — anything else on
# ``record.__dict__`` was added by a caller's ``extra={...}`` and is a
# candidate for redaction below. Built from a throwaway record rather than
# hand-copied so it can't drift from whatever attributes this Python/
# logging version actually sets.
_STANDARD_LOG_RECORD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
) | {"message", "asctime"}


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_ATTRS
        }
        if extra:
            payload["extra"] = redact_mapping(extra)

        return json.dumps(payload, default=str)
