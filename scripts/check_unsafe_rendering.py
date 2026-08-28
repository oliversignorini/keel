#!/usr/bin/env python3
"""Unsafe-rendering lint (docs/boundary-guardrails.md "Unsafe rendering").

Bandit already flags ``mark_safe``/``SafeString`` in ``.py`` files
(B308/B703, active per ``[tool.bandit]`` in ``apps/api/pyproject.toml``),
but bandit does not scan Django templates, so a template ``|safe`` filter
has no automated gate at all. This script is the one gate that covers all
three unsafe-rendering primitives — ``mark_safe(``, ``SafeString(`` and
``|safe`` — in both ``.py`` and ``.html`` files, redundant with bandit on
the Python half by design (defense in depth costs nothing here) and the
sole gate on the template half.

There is currently no legitimate use of any of the three anywhere in
``apps/api`` — this rule is preventative, documenting that no such path
exists. If a real one is ever needed, the escape hatch is a same-line
comment:

    some_html = mark_safe(value)  # unsafe-rendering: <reason>
    {{ value|safe }}{# unsafe-rendering: <reason> #}

Mirrors ``check_permission_lint.py``'s shape: a source-text grep over
``apps/api/keel``, test/migration directories exempt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
KEEL_DIR = API_DIR / "keel"

ESCAPE_HATCH = re.compile(r"unsafe-rendering:\s*\S")

PY_PATTERNS = {
    "mark_safe(": re.compile(r"\bmark_safe\("),
    "SafeString(": re.compile(r"\bSafeString\("),
}

TEMPLATE_PATTERN = re.compile(r"\|\s*safe\b")


def _is_exempt(path: Path) -> bool:
    parts = path.relative_to(KEEL_DIR).parts
    return "tests" in parts or "migrations" in parts


def find_violations() -> list[str]:
    violations: list[str] = []

    for path in sorted(KEEL_DIR.rglob("*.py")):
        if _is_exempt(path):
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if ESCAPE_HATCH.search(line):
                continue
            for label, pattern in PY_PATTERNS.items():
                if pattern.search(line):
                    rel = path.relative_to(API_DIR).as_posix()
                    violations.append(f"{rel}:{line_no}: {label} without an `# unsafe-rendering:` justification")

    for path in sorted(KEEL_DIR.rglob("*.html")):
        if _is_exempt(path):
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if ESCAPE_HATCH.search(line):
                continue
            if TEMPLATE_PATTERN.search(line):
                rel = path.relative_to(API_DIR).as_posix()
                violations.append(f"{rel}:{line_no}: |safe without an `{{# unsafe-rendering: ... #}}` justification")

    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Unsafe-rendering lint failed (docs/boundary-guardrails.md):")
        for violation in violations:
            print(f"  - {violation}")
        print(
            "\nmark_safe(), SafeString() and template |safe bypass Django's autoescaping. "
            "If this use is genuinely safe, justify it with a same-line "
            "`# unsafe-rendering: <reason>` (or `{# unsafe-rendering: <reason> #}` in a template)."
        )
        return 1
    print("Unsafe-rendering lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
