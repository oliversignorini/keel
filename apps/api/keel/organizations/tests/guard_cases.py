"""Declarative table of guard test cases (meta-test 1).

Test modules register cases with ``@allow_case(code)`` / ``@deny_case(code,
reason)`` at import time — during pytest collection, before any test runs
— so ``ALLOW_CASES`` / ``DENY_CASES`` are fully populated regardless of
which test module pytest happens to execute first or last. The meta-test
in ``test_meta_guard_coverage.py`` reads these two lists directly; it does
not depend on test execution order.

The shared parametrized runners in ``test_permissions.py`` assert
``decision.reason == case.reason`` for every deny case, so a deny case
cannot be declared without a reason assertion — PRD invariant 2's "the
deny test must assert the reason" is structural, not a convention someone
can forget.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Builder = Callable[[], tuple[Any, Any, Any | None]]


@dataclass(frozen=True)
class AllowCase:
    code: str
    build: Builder
    label: str


@dataclass(frozen=True)
class DenyCase:
    code: str
    reason: str
    build: Builder
    label: str


ALLOW_CASES: list[AllowCase] = []
DENY_CASES: list[DenyCase] = []


def allow_case(code: str, label: str | None = None) -> Callable[[Builder], Builder]:
    def decorator(build: Builder) -> Builder:
        ALLOW_CASES.append(AllowCase(code=code, build=build, label=label or build.__name__))
        return build

    return decorator


def deny_case(code: str, reason: str, label: str | None = None) -> Callable[[Builder], Builder]:
    def decorator(build: Builder) -> Builder:
        DENY_CASES.append(
            DenyCase(code=code, reason=reason, build=build, label=label or build.__name__)
        )
        return build

    return decorator
