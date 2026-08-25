#!/usr/bin/env python3
"""Per-directory coverage gate (PRD §4, architecture invariant 7).

``coverage.json`` and ``--cov-fail-under`` give one number for a whole run.
This reads a table of glob -> required percentage from
``[tool.keel.coverage]`` in ``apps/api/pyproject.toml`` and checks each glob
against ``apps/api/coverage.json`` (produced by ``pytest --cov-report=json``)
independently.

Rules, stated once because they are easy to get backwards:
- A path matched by no glob is reported and does NOT fail the build — a
  new file with no configured obligation yet is not this script's problem.
- A glob matching no path DOES fail the build — a renamed or deleted
  directory that left its coverage obligation behind is exactly the bug
  this script exists to catch.
"""

from __future__ import annotations

import json
import sys
import tomllib
from fnmatch import fnmatch
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
PYPROJECT_PATH = API_DIR / "pyproject.toml"
COVERAGE_JSON_PATH = API_DIR / "coverage.json"


def load_thresholds(pyproject_path: Path) -> dict[str, float]:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return data.get("tool", {}).get("keel", {}).get("coverage", {})


def load_file_coverage(coverage_json_path: Path) -> dict[str, dict]:
    data = json.loads(coverage_json_path.read_text(encoding="utf-8"))
    return {path.replace("\\", "/"): info for path, info in data["files"].items()}


def percent_for_glob(glob: str, files: dict[str, dict]) -> float | None:
    """Aggregate covered/total lines across every file matching glob.

    Returns None if nothing matched.
    """
    matched = [info for path, info in files.items() if fnmatch(path, glob)]
    if not matched:
        return None
    covered = sum(info["summary"]["covered_lines"] for info in matched)
    total = sum(info["summary"]["num_statements"] for info in matched)
    return (covered / total * 100) if total else 100.0


def check(thresholds: dict[str, float], files: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Return (failures, notes)."""
    failures: list[str] = []

    matched_paths: set[str] = set()
    for glob in thresholds:
        for path in files:
            if fnmatch(path, glob):
                matched_paths.add(path)

    for glob, required in sorted(thresholds.items()):
        actual = percent_for_glob(glob, files)
        if actual is None:
            failures.append(
                f"{glob}: matched no files (required {required}%) - "
                "renamed or deleted path left its coverage obligation behind?"
            )
        elif actual < required:
            failures.append(f"{glob}: {actual:.1f}% actual, {required}% required")

    notes = [
        f"{path}: not covered by any [tool.keel.coverage] glob"
        for path in sorted(set(files) - matched_paths)
    ]

    return failures, notes


def main() -> int:
    if not COVERAGE_JSON_PATH.exists():
        print(
            f"error: {COVERAGE_JSON_PATH} not found - run "
            "`uv run pytest` in apps/api first (it writes coverage.json).",
            file=sys.stderr,
        )
        return 1

    thresholds = load_thresholds(PYPROJECT_PATH)
    files = load_file_coverage(COVERAGE_JSON_PATH)

    failures, notes = check(thresholds, files)

    for note in notes:
        print(f"note: {note}")

    if failures:
        print("\nCoverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("Coverage gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
