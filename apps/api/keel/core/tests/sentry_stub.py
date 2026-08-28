"""A capturing Sentry ``Transport`` — no DSN
exists for this project, so every Sentry-shape assertion in the test
suite swaps this in via ``keel.core.sentry.init_sentry(transport=...)``
instead of requiring a live project."""

from typing import Any

from sentry_sdk.transport import Transport


class CapturingTransport(Transport):
    def __init__(self) -> None:
        super().__init__({"dsn": "http://public@example.com/1"})
        self.envelopes: list[Any] = []

    def capture_envelope(self, envelope: Any) -> None:
        self.envelopes.append(envelope)
