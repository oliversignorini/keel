"""Always-visible CI output for the tenant-isolation meta-test (phase-3.md
A.5; PRD §4 invariant 7): "CI prints every GLOBAL_JUSTIFICATION in the
test output" — using ``pytest_terminal_summary`` rather than plain
``print()`` because it renders regardless of pytest's default output
capturing, so it shows up in a normal (non ``-s``) CI run.

Driven by ``keel.core.authz.registered_global_resources()`` rather
than a router walk, so a ``GlobalResource`` mounted on any router — or on
none at all — still gets its justification printed here (PRD §4
invariant 7).
"""

from typing import Any

from keel.organizations.tests.ninja_tenant_isolation import iter_global_justifications


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    terminalreporter.section("GLOBAL_JUSTIFICATION (org-scoping exemptions, PRD §4 invariant 7)")
    justifications = list(iter_global_justifications())
    if not justifications:
        terminalreporter.write_line("(no GlobalResource with organization_scoped = False found.)")
        return
    for name, justification in justifications:
        terminalreporter.write_line(f"{name}: {justification}")
