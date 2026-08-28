#!/usr/bin/env python3
"""Permission-check placement lint (PRD §4 invariant 2).

"Authorization is expressed only in organizations/permissions.py."
``keel/core/authz.py`` defines the *vocabulary* (``Decision``, the
``Guard`` protocol, the registry) but constructs no ``Decision`` and
registers no guard itself — every real guard implementation lives in
``organizations/permissions.py``, which is the only file allowed to call
``Decision.allow(``, ``Decision.deny(`` or ``registry.register(``.

This is mostly a source-text grep rather than an AST walk: the property
being enforced is "does this string appear in a file other than the one
sanctioned file", and a regex answers that directly. ``Decision.allow(``
and ``Decision.deny(`` are unambiguous, so a plain grep is right for them.

``registry.register(`` is not. There is a second, entirely unrelated
registry — ``keel.jobs.registry``, which registers job *types* and
shares the method name by coincidence. A bare grep flagged
``keel/jobs/demo.py`` as an authorization violation, which is a false
positive that would have been "fixed" by renaming perfectly good job code
or, worse, by exempting a path and blunting the rule. So that one pattern
is import-aware: it only fires in a module that actually binds ``registry``
from ``keel.core.authz``.

Test files are exempt: they legitimately construct ``Decision`` objects and
register fixture guards to exercise the vocabulary itself (see
keel/core/tests/test_authz.py), which is testing the mechanism, not
expressing a real permission check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
KEEL_DIR = API_DIR / "keel"

ALLOWED_FILES = {
    KEEL_DIR / "organizations" / "permissions.py",
}

PATTERNS = {
    "Decision.allow(": re.compile(r"Decision\.allow\("),
    "Decision.deny(": re.compile(r"Decision\.deny\("),
}

# Only meaningful in a module that binds `registry` from the authorization
# vocabulary. keel.jobs.registry exports a `registry` of the same shape for
# job types and is none of this rule's business.
AUTHZ_REGISTRY_PATTERN = re.compile(r"registry\.register\(")
AUTHZ_REGISTRY_IMPORT = re.compile(
    r"^from\s+keel\.core\.authz\s+import\s+.*(?<![\w.])registry(?![\w])", re.MULTILINE
)


def _is_exempt(path: Path) -> bool:
    if path in ALLOWED_FILES:
        return True
    parts = path.relative_to(KEEL_DIR).parts
    return "tests" in parts or "migrations" in parts


def find_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted(KEEL_DIR.rglob("*.py")):
        if _is_exempt(path):
            continue
        text = path.read_text(encoding="utf-8")
        binds_authz_registry = bool(AUTHZ_REGISTRY_IMPORT.search(text))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    rel = path.relative_to(API_DIR).as_posix()
                    violations.append(f"{rel}:{line_no}: {label} outside organizations/permissions.py")
            if binds_authz_registry and AUTHZ_REGISTRY_PATTERN.search(line):
                rel = path.relative_to(API_DIR).as_posix()
                violations.append(
                    f"{rel}:{line_no}: registry.register( outside organizations/permissions.py"
                )
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Permission-check placement lint failed (PRD §4 invariant 2):")
        for violation in violations:
            print(f"  - {violation}")
        print(
            "\nPermission decisions and guard registration may only appear in "
            "apps/api/keel/organizations/permissions.py."
        )
        return 1
    print("Permission-check placement lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
