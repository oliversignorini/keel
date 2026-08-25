"""Always-visible CI output for the tenant-isolation meta-test (phase-3.md
A.5; PRD §4 invariant 7): "CI prints every GLOBAL_JUSTIFICATION in the
test output" — using ``pytest_terminal_summary`` rather than plain
``print()`` because it renders regardless of pytest's default output
capturing, so it shows up in a normal (non ``-s``) CI run.
"""

from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

from keel.organizations.tests.tenant_isolation import iter_global_justifications


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    terminalreporter.section("GLOBAL_JUSTIFICATION (org-scoping exemptions, PRD §4 invariant 7)")
    router_path = getattr(settings, "KEEL_API_ROUTER", "")
    if not router_path:
        terminalreporter.write_line("(KEEL_API_ROUTER not configured — no router to walk yet.)")
        return
    router = import_string(router_path)
    justifications = list(iter_global_justifications(router))
    if not justifications:
        terminalreporter.write_line("(no GlobalViewSet with organization_scoped = False found.)")
        return
    for name, justification in justifications:
        terminalreporter.write_line(f"{name}: {justification}")
