#!/usr/bin/env python3
"""Local, additive-only backward-compatibility gate for ``openapi.merged.json``
(ddia review finding 25).

The existing CI gates (``api-client-generation``, ``contracts``) only prove
the merged spec and the generated client agree with each other *at HEAD* —
neither compares the new spec against the *previous* one, so nothing stops
a path, an operation, a response field, or an enum value from disappearing,
or a request field from becoming newly required, even though Django on
Railway and Next.js on Vercel deploy independently and there is always a
window where old browser JS talks to a new API.

Per ``docs/plans/phase-16.md`` 16.D's philosophy ("the repo runs on a free
GitHub Actions plan ... run gates before they reach CI, not by adding more
Actions minutes for them") this is a plain local script, not a new
workflow job — wire it into the pre-push hook layer phase 16 adds, or run
it by hand before opening a PR that touches ``/api/v1``:

    uv run --project apps/api python scripts/check_openapi_compat.py [--against REF]

``--against`` is any git revision that has ``openapi.merged.json`` at its
current path (default: ``HEAD``'s merge-base with ``origin/master``, falling
back to ``HEAD~1`` outside a clone with that remote). The *working tree's*
copy of the file is always the "new" side, so this also catches an
uncommitted change before it's even pushed.

Rules enforced (additive-only for ``/api/v1`` — this project's own
surface; allauth's ``/_allauth/...`` half is upstream's contract, not
ours, and is only checked for path/operation removal):

1. No path is removed.
2. No operation (method) on a surviving path is removed.
3. No property disappears from a request or response schema that
   previously had it (a client holding the old shape must still parse).
4. No property becomes newly required on a request body (an old client's
   payload, valid before, must not start failing validation).
5. No enum value is removed from a schema that had it (a client that
   still sends/expects the old value must not start seeing a new error).

This is deliberately conservative rather than exhaustive — it is meant to
catch the mistakes named above, not to be a full OpenAPI-diff tool.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "openapi.merged.json"
SPEC_GIT_PATH = "openapi.merged.json"


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _default_baseline() -> str:
    try:
        return _run_git("merge-base", "HEAD", "origin/master")
    except subprocess.CalledProcessError:
        return "HEAD~1"


def _load_baseline_spec(ref: str) -> dict[str, Any] | None:
    try:
        raw = _run_git("show", f"{ref}:{SPEC_GIT_PATH}")
    except subprocess.CalledProcessError:
        return None
    return json.loads(raw)


def _resolve(schema: dict[str, Any], components: dict[str, Any], seen: frozenset[str]) -> dict:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        return schema
    name = ref[len(prefix) :]
    if name in seen:
        return {}  # cycle guard — this checker doesn't need to recurse through it
    target = components.get("schemas", {}).get(name)
    if not isinstance(target, dict):
        return {}
    return _resolve(target, components, seen | {name})


def _properties(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve(schema, components, frozenset())
    return resolved.get("properties", {}) or {}


def _required(schema: dict[str, Any], components: dict[str, Any]) -> set[str]:
    resolved = _resolve(schema, components, frozenset())
    return set(resolved.get("required", []) or [])


def _enum_values(schema: dict[str, Any], components: dict[str, Any]) -> list[Any] | None:
    resolved = _resolve(schema, components, frozenset())
    return resolved.get("enum")


def _json_schema_of(body_or_response: dict[str, Any]) -> dict[str, Any] | None:
    content = body_or_response.get("content", {})
    media = content.get("application/json")
    if not media:
        return None
    return media.get("schema")


def _iter_schema_pairs(
    old_schema: dict[str, Any] | None,
    new_schema: dict[str, Any] | None,
    old_components: dict[str, Any],
    new_components: dict[str, Any],
    seen: set[tuple[int, int]],
) -> list[tuple[dict, dict]]:
    """Depth-limited pairing of (old, new) schema nodes reachable through
    `properties`, for the enum-narrowing check. Not a full structural walk
    (arrays/`allOf`/`anyOf` aren't followed) — deliberately conservative,
    see module docstring."""
    if old_schema is None or new_schema is None:
        return []
    key = (id(old_schema), id(new_schema))
    if key in seen:
        return []
    seen.add(key)

    old_resolved = _resolve(old_schema, old_components, frozenset())
    new_resolved = _resolve(new_schema, new_components, frozenset())
    pairs = [(old_resolved, new_resolved)]
    for name, old_prop in (old_resolved.get("properties") or {}).items():
        new_prop = (new_resolved.get("properties") or {}).get(name)
        if new_prop is not None:
            pairs.extend(
                _iter_schema_pairs(old_prop, new_prop, old_components, new_components, seen)
            )
    return pairs


def check(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    old_paths = old.get("paths", {}) or {}
    new_paths = new.get("paths", {}) or {}
    old_components = old.get("components", {}) or {}
    new_components = new.get("components", {}) or {}

    for path, old_methods in old_paths.items():
        new_methods = new_paths.get(path)
        if new_methods is None:
            violations.append(f"removed path: {path}")
            continue
        for method, old_operation in old_methods.items():
            if not isinstance(old_operation, dict):
                continue
            new_operation = new_methods.get(method)
            if new_operation is None:
                violations.append(f"removed operation: {method.upper()} {path}")
                continue
            if not path.startswith("/api/v1"):
                continue  # allauth's own contract — only checked for removal, above

            op_label = f"{method.upper()} {path}"

            old_body = _json_schema_of(
                (old_operation.get("requestBody") or {})
            )
            new_body = _json_schema_of(
                (new_operation.get("requestBody") or {})
            )
            if old_body is not None and new_body is not None:
                old_required = _required(old_body, old_components)
                new_required = _required(new_body, new_components)
                newly_required = new_required - old_required
                if newly_required:
                    violations.append(
                        f"{op_label}: request body field(s) newly required: "
                        f"{sorted(newly_required)}"
                    )
                old_props = _properties(old_body, old_components)
                new_props = _properties(new_body, new_components)
                missing = set(old_props) - set(new_props)
                if missing:
                    violations.append(
                        f"{op_label}: request body field(s) removed: {sorted(missing)}"
                    )

            for status, old_response in (old_operation.get("responses") or {}).items():
                new_response = (new_operation.get("responses") or {}).get(status)
                if new_response is None:
                    if status not in ("default",):
                        violations.append(f"{op_label}: removed response {status}")
                    continue
                old_schema = _json_schema_of(old_response)
                new_schema = _json_schema_of(new_response)
                if old_schema is None or new_schema is None:
                    continue
                old_props = _properties(old_schema, old_components)
                new_props = _properties(new_schema, new_components)
                missing = set(old_props) - set(new_props)
                if missing:
                    violations.append(
                        f"{op_label}: response {status} field(s) removed: {sorted(missing)}"
                    )

            seen: set[tuple[int, int]] = set()
            schema_pairs = list(
                _iter_schema_pairs(old_body, new_body, old_components, new_components, seen)
            )
            for status, old_response in (old_operation.get("responses") or {}).items():
                new_response = (new_operation.get("responses") or {}).get(status)
                if new_response is None:
                    continue
                schema_pairs.extend(
                    _iter_schema_pairs(
                        _json_schema_of(old_response),
                        _json_schema_of(new_response),
                        old_components,
                        new_components,
                        seen,
                    )
                )
            for old_node, new_node in schema_pairs:
                old_enum = old_node.get("enum")
                if old_enum is None:
                    continue
                new_enum = new_node.get("enum") or []
                removed_values = set(old_enum) - set(new_enum)
                if removed_values:
                    violations.append(
                        f"{op_label}: enum value(s) removed: {sorted(removed_values, key=str)}"
                    )

    return violations


def main() -> int:
    args = sys.argv[1:]
    baseline_ref = _default_baseline()
    if args and args[0] == "--against":
        baseline_ref = args[1]

    if not SPEC_PATH.exists():
        print(f"{SPEC_PATH} does not exist — run scripts/merge_openapi.py first.")
        return 1

    old_spec = _load_baseline_spec(baseline_ref)
    if old_spec is None:
        print(
            f"No {SPEC_GIT_PATH} at {baseline_ref!r} — nothing to compare against "
            "(first commit that adds it, or a shallow clone). Passing by default."
        )
        return 0

    new_spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    violations = check(old_spec, new_spec)

    if violations:
        print(f"openapi.merged.json is not additive-only relative to {baseline_ref}:\n")
        for violation in violations:
            print(f"  - {violation}")
        print(
            "\nThe /api/v1 rule (docs/adr/0002-auth-bff-shape.md; ddia review finding 25): "
            "add fields, never rename or remove; deprecate before removing; never tighten "
            "an existing request field. If this break is intentional (a documented major "
            "version bump), note that in the PR description — this script has no override "
            "flag on purpose, so that decision stays visible rather than silently skipped."
        )
        return 1

    print(f"openapi.merged.json is additive-only relative to {baseline_ref}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
