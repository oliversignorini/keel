"""Audit decorators (PRD v1.2, Phase 8, "The service registry, specified").

``@audited(action)`` marks a mutating service function so its call is
recorded — on commit, never inline, matching the transaction discipline
in PRD §4 invariant 3 — and registers the function in a module-level
registry. ``@not_audited(reason)`` is the explicit escape hatch for a
mutating function that deliberately isn't recorded, registered with its
reason so the choice is visible rather than silent.

There are no services to decorate yet in Phase 1 — ``keel.audit.AuditLog``
gets its table in the baseline migration (task 1.10), but nothing writes
to it until Phase 8 wires ``set_recorder`` to a real writer. What Phase 1
proves is that the decorators record correctly and register correctly,
against fixture functions.

The registry is walkable (module-level ``registry``, iterable as
``(qualified_name, entry)`` pairs) — Phase 8's meta-test enumerates every
marked function and its marker the same way Phase 3's meta-test walks
``keel.core.authz.registry``.
"""

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, TypeVar

from django.db import transaction

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class AuditRecord:
    action: str
    actor: Any = None
    impersonator: Any = None
    target: Any = None
    metadata: dict[str, Any] | None = None


def _default_recorder(record: AuditRecord) -> None:
    """No-op until Phase 8 installs the real AuditLog writer."""


_recorder: Callable[[AuditRecord], None] = _default_recorder


def set_recorder(fn: Callable[[AuditRecord], None]) -> None:
    """Install the function that persists an ``AuditRecord``.

    A settings-configured seam, same shape as
    ``keel.core.authz``'s membership resolver: Phase 8 calls this once,
    at app-ready time, with a function that writes to ``AuditLog``. Tests
    call it too, to capture records without touching the database.
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

    def __iter__(self):
        return iter(self._entries.items())

    def __len__(self) -> int:
        return len(self._entries)


registry = AuditRegistry()


def audited(action: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        registry.register_audited(func, action)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            record = AuditRecord(
                action=action,
                actor=kwargs.get("actor"),
                impersonator=kwargs.get("impersonator"),
                target=kwargs.get("target", result),
                metadata=kwargs.get("metadata"),
            )
            transaction.on_commit(lambda: _recorder(record))
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def not_audited(reason: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        registry.register_not_audited(func, reason)
        return func

    return decorator
