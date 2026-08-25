#!/usr/bin/env python3
"""Deterministically merge the two OpenAPI documents this project serves
(PRD §7, §8 Phase 2 A.3) into one file for client generation.

- ``drf-spectacular`` describes ``/api/v1/…`` (this project's own DRF
  views).
- ``django-allauth`` headless describes ``/_allauth/browser/v1/…`` (PRD §4
  "Auth architecture": "allauth's headless flow ... also serves its own
  OpenAPI specification").

Neither generator knows about the other, so this script builds both specs
in-process (no HTTP round trip — a running server is not required) and
combines them into a single document at ``openapi.merged.json``, which
``packages/api-client``'s ``orval`` config reads.

Determinism matters more than most scripts: if the merge reordered keys
run to run, a "generated client is stale" CI check would fail randomly on
unrelated changes and eventually just get disabled (docs/plans/phase-2.md
A.3). The only thing that makes that true here is ``sort_keys=True`` on
the final dump — every dict-building step above it is free to produce
keys in whatever order Python felt like, because the last step erases it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "apps" / "api"
OUTPUT_PATH = REPO_ROOT / "openapi.merged.json"

# Component sub-objects that can hold named, $ref-able definitions and so
# need collision handling when two specs are combined (OpenAPI 3.0 §4.7.15).
COMPONENT_KINDS = (
    "schemas",
    "parameters",
    "responses",
    "examples",
    "requestBodies",
    "headers",
    "securitySchemes",
)


def _rename_refs(node: Any, kind: str, renames: dict[str, str]) -> None:
    """Rewrite ``$ref: '#/components/<kind>/<old>'`` in place wherever
    ``old`` was renamed to avoid a collision with the base spec."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            prefix = f"#/components/{kind}/"
            if ref.startswith(prefix):
                name = ref[len(prefix) :]
                if name in renames:
                    node["$ref"] = prefix + renames[name]
        for value in node.values():
            _rename_refs(value, kind, renames)
    elif isinstance(node, list):
        for item in node:
            _rename_refs(item, kind, renames)


def _namespace_collisions(extra: dict, base_components: dict, extra_label: str) -> None:
    """Prefix any ``extra`` component name that collides with ``base``'s,
    rewriting every ``$ref`` inside ``extra`` that pointed at the old name.
    The two source specs never reference each other's components, so refs
    outside ``extra`` never need touching."""
    extra_components = extra.get("components", {})
    for kind in COMPONENT_KINDS:
        base_names = set(base_components.get(kind, {}) or {})
        extra_kind = extra_components.get(kind)
        if not extra_kind:
            continue
        renames = {name: f"{extra_label}{name}" for name in extra_kind if name in base_names}
        if not renames:
            continue
        for old_name, new_name in renames.items():
            extra_kind[new_name] = extra_kind.pop(old_name)
        _rename_refs(extra, kind, renames)


def _merge_components(base: dict, extra: dict) -> dict:
    merged = {kind: dict(base.get(kind, {}) or {}) for kind in COMPONENT_KINDS}
    for kind in COMPONENT_KINDS:
        merged[kind].update(extra.get(kind, {}) or {})
    return {kind: value for kind, value in merged.items() if value}


def _merge_tags(base_tags: list[dict], extra_tags: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {tag["name"]: tag for tag in base_tags}
    for tag in extra_tags:
        merged.setdefault(tag["name"], tag)
    return list(merged.values())


def merge(base: dict, extra: dict, extra_label: str) -> dict:
    """Merge ``extra`` into ``base``, returning a new document. ``base``
    and ``extra`` must describe disjoint sets of paths."""
    base_components = base.get("components", {}) or {}
    _namespace_collisions(extra, base_components, extra_label)

    overlap = set(base.get("paths", {})) & set(extra.get("paths", {}))
    if overlap:
        raise ValueError(f"Both OpenAPI sources define the same path(s): {sorted(overlap)}")

    return {
        "openapi": base["openapi"],
        "info": base["info"],
        "paths": {**base.get("paths", {}), **extra.get("paths", {})},
        "components": _merge_components(base_components, extra.get("components", {}) or {}),
        "tags": _merge_tags(base.get("tags", []), extra.get("tags", [])),
    }


def build_drf_spec() -> dict:
    from drf_spectacular.generators import SchemaGenerator

    generator = SchemaGenerator()
    generator.coerce_path_pk = True
    return generator.get_schema(request=None, public=True)


def build_allauth_spec() -> dict:
    # allauth.headless.adapter.DefaultHeadlessAdapter.get_user_dataclass()
    # calls uuid.uuid4() to produce the "id" field's OpenAPI example every
    # time the schema is built — a random value baked into the spec on
    # every run. Freeze it for the duration of the build so the merged
    # document is byte-identical run to run, per this script's docstring.
    import uuid

    from allauth.headless.spec.internal.schema import get_schema

    frozen_uuid = uuid.UUID("00000000-0000-7000-8000-000000000000")
    real_uuid4 = uuid.uuid4
    uuid.uuid4 = lambda: frozen_uuid  # type: ignore[assignment]
    try:
        return get_schema()
    finally:
        uuid.uuid4 = real_uuid4


def main() -> int:
    sys.path.insert(0, str(API_DIR))
    import django
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

    drf_spec = build_drf_spec()
    allauth_spec = build_allauth_spec()

    merged = merge(drf_spec, allauth_spec, extra_label="Allauth")
    OUTPUT_PATH.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(merged['paths'])} paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
