"""Always-visible CI output for the tenant-isolation meta-test (phase-3.md
A.5; PRD §4 invariant 7): "CI prints every GLOBAL_JUSTIFICATION in the
test output" — using ``pytest_terminal_summary`` rather than plain
``print()`` because it renders regardless of pytest's default output
capturing, so it shows up in a normal (non ``-s``) CI run.

Driven by ``keel.core.authz.registered_global_viewsets()`` (DRF) and,
since phase-10.md 10.C, ``keel.core.ninja_authz.registered_global_resources()``
(Ninja) rather than a router walk, so a ``GlobalViewSet``/``GlobalResource``
registered on any router — or on none at all — still gets its
justification printed here (PRD §4 invariant 7).
"""

from typing import Any

from keel.organizations.tests.ninja_tenant_isolation import (
    iter_global_justifications as iter_ninja_global_justifications,
)
from keel.organizations.tests.tenant_isolation import iter_global_justifications


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    terminalreporter.section("GLOBAL_JUSTIFICATION (org-scoping exemptions, PRD §4 invariant 7)")
    justifications = list(iter_global_justifications()) + list(iter_ninja_global_justifications())
    if not justifications:
        terminalreporter.write_line(
            "(no GlobalViewSet/GlobalResource with organization_scoped = False found.)"
        )
        return
    for name, justification in justifications:
        terminalreporter.write_line(f"{name}: {justification}")
