"""Always-visible CI output for the audit meta-test (PRD v1.2 §8 Phase 8;
docs/plans/phase-8.md 8.1): "print every not_audited reason in CI output,
on the same principle as GLOBAL_JUSTIFICATION" —
``pytest_terminal_summary`` rather than plain ``print()`` so it renders
regardless of pytest's default output capturing, the same mechanism
``keel.organizations.tests.conftest`` uses for ``GLOBAL_JUSTIFICATION``.
"""

from typing import Any

from keel.core.tests.service_audit_registry import iter_not_audited_reasons


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    terminalreporter.section("@not_audited reasons (audit meta-test, PRD v1.2 §8 Phase 8)")
    reasons = list(iter_not_audited_reasons())
    if not reasons:
        terminalreporter.write_line("(no @not_audited service found.)")
        return
    for name, reason in reasons:
        terminalreporter.write_line(f"{name}: {reason}")
