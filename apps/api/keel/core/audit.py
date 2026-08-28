"""Audit decorators (PRD v1.2 §8, "The service registry, specified").

``@audited(action)`` marks a mutating service function so its call is
recorded inline, immediately after it returns (ddia#17) — not deferred
to ``transaction.on_commit()``, so the record shares whatever
transaction the effect it describes is already in — and registers the
function in a module-level registry. ``@not_audited(reason)`` is the
explicit escape hatch for a mutating function that deliberately isn't
recorded, registered with its reason so the choice is visible rather
than silent.

``keel.audit.AuditLog`` holds the persisted rows; ``set_recorder`` wires
this module's decorators to the real writer at app-ready time
(``keel/audit/apps.py``).

The registry is walkable (module-level ``registry``, iterable as
``(qualified_name, entry)`` pairs) — the audit meta-test enumerates every
marked function and its marker the same way the permission-guard
meta-test walks ``keel.core.authz.registry``.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class AuditRecord:
    action: str
    actor: Any = None
    impersonator: Any = None
    target: Any = None
    metadata: dict[str, Any] | None = None


def _default_recorder(record: AuditRecord) -> None:
    """No-op default, replaced by the real ``AuditLog`` writer via
    ``set_recorder`` at app-ready time."""


_recorder: Callable[[AuditRecord], None] = _default_recorder


def _default_target(result: Any) -> Any:
    """When a decorated service doesn't pass ``target=`` explicitly, its
    own return value stands in — but a function returning ``(row, extra)``
    (e.g. ``create_presigned_upload`` returning the row plus a presigned
    URL) means ``result`` is a tuple with no ``.pk``, and the recorder
    falls back to ``str(result)`` — which, for a tuple holding a
    signed URL, can exceed ``AuditLog.target_id``'s column width. The
    first element of a tuple return is the actual row in every case in
    this codebase, so unwrap it."""
    if isinstance(result, tuple) and result:
        return result[0]
    return result


def set_recorder(fn: Callable[[AuditRecord], None]) -> None:
    """Install the function that persists an ``AuditRecord``.

    A settings-configured seam, same shape as
    ``keel.core.authz``'s membership resolver: ``keel/audit/apps.py``
    calls this once, at app-ready time, with a function that writes to
    ``AuditLog``. Tests call it too, to capture records without touching
    the database.
    """
    global _recorder
    _recorder = fn


class AuditRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _key(func: Callable[..., Any]) -> str:
        return f"{func.__module__}.{func.__qualname__}"

    def register_audited(self, func: Callable[..., Any], action: str) -> None:
        self._entries[self._key(func)] = {"kind": "audited", "action": action, "func": func}

    def register_not_audited(self, func: Callable[..., Any], reason: str) -> None:
        self._entries[self._key(func)] = {"kind": "not_audited", "reason": reason, "func": func}

    def get(self, func: Callable[..., Any]) -> dict[str, Any]:
        return self._entries[self._key(func)]

    def __iter__(self) -> Iterator[tuple[str, dict[str, Any]]]:
        return iter(self._entries.items())

    def __len__(self) -> int:
        return len(self._entries)


registry = AuditRegistry()


def audited(action: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        registry.register_audited(func, action)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Inline, right after the effect, not deferred to
            # transaction.on_commit() (ddia#17). AuditLog lives in the
            # same Postgres as everything it describes, so a dual write
            # across a commit boundary buys nothing but a window where
            # the business effect is durable and the audit row is gone
            # (process dies between COMMIT and the callback, or the
            # callback's own INSERT fails). on_commit stays the right
            # tool for genuinely external effects (Stripe calls).
            #
            # Deliberately not wrapped in its own transaction.atomic()
            # here: some audited services (e.g.
            # keel.billing.services.create_checkout_session) call Stripe
            # with no surrounding transaction at all, by design (PRD §4
            # invariant 3, "no Stripe call happens inside an open
            # transaction") — a decorator-level atomic would force one.
            # Calling the recorder directly, with no atomic of its own,
            # means: if the caller already has a transaction open (a
            # service calling another audited service, a future
            # ATOMIC_REQUESTS setup), this write joins it and rolls back
            # with everything else; if not, it commits immediately after
            # the effect, same as this codebase's services already do
            # for their own writes.
            result = func(*args, **kwargs)
            record = AuditRecord(
                action=action,
                actor=kwargs.get("actor"),
                impersonator=kwargs.get("impersonator"),
                target=kwargs.get("target", _default_target(result)),
                metadata=kwargs.get("metadata"),
            )
            _recorder(record)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def not_audited(reason: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        registry.register_not_audited(func, reason)
        return func

    return decorator
