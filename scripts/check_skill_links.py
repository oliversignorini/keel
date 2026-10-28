#!/usr/bin/env python3
"""Relative-link lint for the vendored skills under ``.claude/skills/``.

Every skill in there is an *edited* copy of an upstream one: references the
upstream skill shipped were dropped where they described a stack this repo
does not run (DRF permissions, Celery broker topology, shadcn's chat
primitives). Dropping a file is cheap; leaving a link pointing at it is not —
an agent that follows a dead `[foo](./references/foo.md)` reads nothing and
silently proceeds without the guidance the link promised. That failure is
invisible at runtime, which is exactly why it gets a gate.

Checks, per Markdown file under ``.claude/skills/``:

- every relative Markdown link and image target resolves to a file on disk
- the ``license:`` value in a ``SKILL.md`` frontmatter resolves too
- every ``SKILL.md`` carries ``source``, ``source_ref`` and ``license``, and
  ``source_ref`` is a full 40-character SHA (a branch name silently
  un-pins the vendored copy)
- no file still contains the shadcn skill's ``!`...``` command-injection
  syntax, which would run a network command every time the skill is read

External links (``http``/``https``/``mailto``) and in-page anchors are not
followed: this gate is about the integrity of the vendored tree, not about
the internet being up.

Run: ``python scripts/check_skill_links.py``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"

# [text](target) and ![alt](target) — the target stops at whitespace or ')'
# so that "(./x.md)" and "(./x.md 'title')" both yield "./x.md".
LINK = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)")
# The shadcn skill's load-time shell injection: ``!`some command` ``.
INJECTION = re.compile(r"!`[^`]+`")
SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_FRONTMATTER = ("source", "source_ref", "license")


def frontmatter(text: str) -> dict[str, str]:
    """The top-level scalar keys of a leading YAML block. Deliberately not a
    YAML parse: a dependency is not worth it for ``key: value`` lines, and a
    folded multi-line ``description`` is the only nesting these files have —
    its continuation lines are indented, so skipping indented lines is
    enough."""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[4 : end + 1].splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out


def is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#", "//"))


def main() -> int:
    if not SKILLS.is_dir():
        print(f"no skills directory at {SKILLS.relative_to(ROOT)} — nothing to check")
        return 0

    errors: list[str] = []
    checked = 0

    for path in sorted(SKILLS.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        checked += 1

        for match in INJECTION.finditer(text):
            errors.append(
                f"{rel}: load-time command injection {match.group(0)!r} "
                "— replace with a static pointer"
            )

        for match in LINK.finditer(text):
            target = match.group(1).strip("<>")
            if is_external(target):
                continue
            # Strip a trailing anchor: ./cli.md#info -> ./cli.md
            file_part = target.split("#", 1)[0]
            if not file_part:
                continue
            if not (path.parent / file_part).exists():
                errors.append(f"{rel}: dead link -> {target}")

        if path.name != "SKILL.md":
            continue

        meta = frontmatter(text)
        for key in REQUIRED_FRONTMATTER:
            if not meta.get(key):
                errors.append(f"{rel}: frontmatter is missing `{key}`")

        ref = meta.get("source_ref", "")
        if ref and not SHA.match(ref):
            errors.append(
                f"{rel}: source_ref {ref!r} is not a 40-character SHA "
                "— a vendored skill must be pinned"
            )

        license_path = meta.get("license", "")
        if license_path and not is_external(license_path):
            if not (path.parent / license_path).exists():
                errors.append(f"{rel}: license -> {license_path} does not exist")

    if errors:
        summary = f"check_skill_links: {len(errors)} problem(s) in {checked} file(s)"
        print(summary, end="\n\n", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print(f"check_skill_links: OK ({checked} markdown file(s) under .claude/skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
