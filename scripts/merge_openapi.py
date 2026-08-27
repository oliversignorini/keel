#!/usr/bin/env python3
"""Deterministically merge the two OpenAPI documents this project serves
(PRD §7, §8 Phase 2 A.3) into one file for client generation.

- Django Ninja describes ``/api/v1/…`` (this project's own views;
  phase-10.md 10.D — replaced drf-spectacular when the API layer moved
  off DRF).
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

    merged = {
        "openapi": base["openapi"],
        "info": base["info"],
        "paths": {**base.get("paths", {}), **extra.get("paths", {})},
        "components": _merge_components(base_components, extra.get("components", {}) or {}),
        "tags": _merge_tags(base.get("tags", []), extra.get("tags", [])),
    }
    # api-patterns finding 5: document-level `servers`/`security` used to
    # be dropped by construction — neither key was in this dict at all —
    # even though build_ninja_spec() below now produces both. Only `base`
    # (the Ninja spec) sets these; allauth's own schema builder never has,
    # so there is nothing to merge here beyond carrying `base`'s through.
    if "servers" in base:
        merged["servers"] = base["servers"]
    if "security" in base:
        merged["security"] = base["security"]
    return merged



# api-patterns finding 5: how a caller authenticates was published nowhere
# machine-readable — django-ninja itself never emits `security`/
# `securitySchemes`, regardless of a route's real `auth=` callable
# (keel.core.ninja_auth.session_auth / optional_session_auth / none).
# These paths are exactly the ones built with `public_router()` — see
# posd finding 2 — so hand-listing them here, rather than trying to
# introspect Ninja's operation objects, stays honest about what's
# actually a manual annotation and what's derived.
NINJA_PUBLIC_PATHS = {
    "/api/v1/plans/",
    "/api/v1/stripe/webhook/",
}
# optional_session_auth: a session is accepted and used if present
# (invite_accept attributes the acceptance to the logged-in user when
# one exists), but is never required — modelled as "sessionCookie OR no
# security" via the empty `{}` alternative (OpenAPI 3.1 §4.8.30).
NINJA_OPTIONAL_AUTH_PATHS = {
    "/api/v1/invite/{token}/",
}
_SAFE_METHODS = {"get", "head"}


def _apply_ninja_security(spec: dict) -> None:
    spec.setdefault("components", {})["securitySchemes"] = {
        "sessionCookie": {
            "type": "apiKey",
            "in": "cookie",
            "name": "sessionid",
            "description": (
                "The Django session cookie, HttpOnly, set by "
                "/_allauth/browser/v1/auth/login (docs/auth-client-contract.md)."
            ),
        },
        "csrfHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-CSRFToken",
            "description": (
                "Required on every unsafe method (POST/PUT/PATCH/DELETE) once "
                "sessionCookie is presented — read from the non-HttpOnly "
                "csrftoken cookie (docs/auth-client-contract.md 'CSRF token "
                "acquisition')."
            ),
        },
    }
    spec["security"] = [{"sessionCookie": [], "csrfHeader": []}]
    # docs/adr/0002-auth-bff-shape.md: the Next.js BFF is the only intended
    # caller of this document's own origin now — browser code talks to
    # the BFF's same-origin proxy paths instead. "/" documents that
    # relationship rather than a guessed production hostname this
    # template doesn't know yet.
    spec["servers"] = [
        {
            "url": "/",
            "description": (
                "Same-origin, as seen by the Next.js BFF that proxies every "
                "browser request to the real API origin server-side."
            ),
        }
    ]

    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            if path in NINJA_PUBLIC_PATHS:
                operation["security"] = []
            elif path in NINJA_OPTIONAL_AUTH_PATHS:
                operation["security"] = [{"sessionCookie": []}, {}]
            elif method in _SAFE_METHODS:
                operation["security"] = [{"sessionCookie": []}]
            # else: inherits the document-level default set above.


def build_ninja_spec() -> dict:
    from keel.core.ninja_api import api

    # NinjaAPI.get_openapi_schema() returns an OpenAPISchema (a dict
    # subclass with extra behaviour) — coerce to a plain dict so the rest
    # of this script (which round-trips everything through json.dumps)
    # doesn't depend on that subclass's methods surviving the trip.
    schema = dict(api.get_openapi_schema())
    _apply_ninja_security(schema)
    return schema


# allauth headless's own schema (allauth.headless.spec.internal.schema.get_schema)
# sets no `operationId` on any operation, so orval falls back to a name
# derived from method + path (e.g. ``postAllauthBrowserV1AuthLogin``) —
# unstable-reading and a breaking rename risk every time a path changes.
# This assigns a stable, hand-picked name per (method, path) instead, so
# the generated client's function names don't depend on orval's fallback
# heuristic. Phase 2's web code (apps/web/app/(auth)/*, lib/auth/*) was
# built against these exact names.
ALLAUTH_OPERATION_IDS: dict[tuple[str, str], str] = {
    ("get", "/_allauth/browser/v1/account/authenticators"): "authenticatorsList",
    ("get", "/_allauth/browser/v1/account/authenticators/recovery-codes"): "recoveryCodesGet",
    ("post", "/_allauth/browser/v1/account/authenticators/recovery-codes"): "recoveryCodesRegenerate",
    ("get", "/_allauth/browser/v1/account/authenticators/totp"): "totpGet",
    ("post", "/_allauth/browser/v1/account/authenticators/totp"): "totpActivate",
    ("delete", "/_allauth/browser/v1/account/authenticators/totp"): "totpDeactivate",
    ("get", "/_allauth/browser/v1/account/email"): "emailList",
    ("post", "/_allauth/browser/v1/account/email"): "emailAdd",
    ("put", "/_allauth/browser/v1/account/email"): "emailChangePrimary",
    ("patch", "/_allauth/browser/v1/account/email"): "emailRequestVerification",
    ("delete", "/_allauth/browser/v1/account/email"): "emailRemove",
    ("post", "/_allauth/browser/v1/account/password/change"): "accountPasswordChange",
    ("get", "/_allauth/browser/v1/account/phone"): "phoneGet",
    ("post", "/_allauth/browser/v1/account/phone"): "phoneChange",
    ("get", "/_allauth/browser/v1/account/providers"): "providersList",
    ("delete", "/_allauth/browser/v1/account/providers"): "providersDisconnect",
    ("post", "/_allauth/browser/v1/auth/2fa/authenticate"): "authMfaAuthenticate",
    ("post", "/_allauth/browser/v1/auth/2fa/reauthenticate"): "authMfaReauthenticate",
    ("post", "/_allauth/browser/v1/auth/code/confirm"): "authCodeConfirm",
    ("get", "/_allauth/browser/v1/auth/email/verify"): "authEmailVerifyInfo",
    ("post", "/_allauth/browser/v1/auth/email/verify"): "authEmailVerify",
    ("post", "/_allauth/browser/v1/auth/email/verify/resend"): "authEmailVerifyResend",
    ("post", "/_allauth/browser/v1/auth/login"): "authLogin",
    ("post", "/_allauth/browser/v1/auth/password/request"): "authPasswordRequest",
    ("get", "/_allauth/browser/v1/auth/password/reset"): "authPasswordResetInfo",
    ("post", "/_allauth/browser/v1/auth/password/reset"): "authPasswordReset",
    ("post", "/_allauth/browser/v1/auth/phone/verify"): "authPhoneVerify",
    ("post", "/_allauth/browser/v1/auth/phone/verify/resend"): "authPhoneVerifyResend",
    ("post", "/_allauth/browser/v1/auth/provider/redirect"): "authProviderRedirect",
    ("get", "/_allauth/browser/v1/auth/provider/signup"): "authProviderSignupInfo",
    ("post", "/_allauth/browser/v1/auth/provider/signup"): "authProviderSignup",
    ("post", "/_allauth/browser/v1/auth/provider/token"): "authProviderToken",
    ("post", "/_allauth/browser/v1/auth/reauthenticate"): "authReauthenticate",
    ("get", "/_allauth/browser/v1/auth/session"): "authGetSession",
    ("delete", "/_allauth/browser/v1/auth/session"): "authLogout",
    ("get", "/_allauth/browser/v1/auth/sessions"): "sessionsList",
    ("delete", "/_allauth/browser/v1/auth/sessions"): "sessionsRevoke",
    ("post", "/_allauth/browser/v1/auth/signup"): "authSignup",
    ("get", "/_allauth/browser/v1/config"): "authConfig",
}


def _normalize_nullable_to_31(node: Any) -> None:
    """Rewrite OpenAPI 3.0-style ``{"nullable": true, ...}`` into the
    OpenAPI 3.1 / JSON Schema 2020-12 shape ``{"anyOf": [{...}, {"type":
    "null"}]}``, in place, recursively.

    allauth headless's own schema generator (``allauth.headless.spec``)
    predates 3.1 and still emits the 3.0 keyword; Ninja emits real 3.1
    (stage 10.D's finding — see the ADR / phase-10 report). A document
    declaring ``"openapi": "3.1.0"`` throughout is otherwise fine mixed
    dialect-wise for every case tested (orval 7.21 resolves Ninja's own
    ``anyOf``-with-``null`` fields correctly) — the one real gap found
    was exactly this: ``nullable: true`` beside a bare ``$ref`` is a
    3.1-invalid combination (2020-12 doesn't define ``nullable`` at all,
    and sibling keys next to a ``$ref`` are ignored by spec), so orval's
    3.1-mode parser silently drops the null-ness instead of erroring.
    Fixed at the source here rather than left as a known gap.
    """
    if isinstance(node, dict):
        if node.get("nullable") is True:
            del node["nullable"]
            inner = {k: v for k, v in node.items()}
            node.clear()
            node["anyOf"] = [inner, {"type": "null"}]
            _normalize_nullable_to_31(inner)
            return
        for value in node.values():
            _normalize_nullable_to_31(value)
    elif isinstance(node, list):
        for item in node:
            _normalize_nullable_to_31(item)


# Endpoints reachable with no session at all — the rest default to
# requiring sessionCookie (+ csrfHeader on unsafe methods), same as the
# Ninja half. "Optional" flows (2FA/reauthenticate/code-confirm resolve a
# *pending*, partially-authenticated session, which still carries a
# sessionCookie — they are not the "no cookie at all" case this set means).
PUBLIC_ALLAUTH_OPERATION_IDS = {
    "authConfig",
    "authGetSession",  # the priming GET; 401 with no session is the documented case
    "authSignup",
    "authLogin",
    "authPasswordRequest",
    "authPasswordResetInfo",
    "authPasswordReset",
    "authEmailVerifyInfo",
    "authEmailVerify",
    "authEmailVerifyResend",
    "authProviderRedirect",
    "authProviderSignupInfo",
    "authProviderSignup",
    "authProviderToken",
}


def _apply_allauth_security(spec: dict) -> None:
    for methods in spec.get("paths", {}).values():
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id in PUBLIC_ALLAUTH_OPERATION_IDS:
                operation["security"] = []
            elif method in _SAFE_METHODS:
                operation["security"] = [{"sessionCookie": []}]
            else:
                operation["security"] = [{"sessionCookie": [], "csrfHeader": []}]


def _assign_allauth_operation_ids(spec: dict) -> None:
    missing: list[str] = []
    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            operation_id = ALLAUTH_OPERATION_IDS.get((method, path))
            if operation_id is None:
                missing.append(f"{method.upper()} {path}")
                continue
            operation["operationId"] = operation_id
    if missing:
        raise ValueError(
            "ALLAUTH_OPERATION_IDS is missing an entry for: "
            + ", ".join(sorted(missing))
            + " — add one (scripts/merge_openapi.py) so orval doesn't fall "
            "back to an unstable generated name."
        )


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
        schema = get_schema()
    finally:
        uuid.uuid4 = real_uuid4
    _assign_allauth_operation_ids(schema)
    _apply_allauth_security(schema)
    _normalize_nullable_to_31(schema)
    return schema


def main() -> int:
    sys.path.insert(0, str(API_DIR))
    import django
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

    ninja_spec = build_ninja_spec()
    allauth_spec = build_allauth_spec()

    merged = merge(ninja_spec, allauth_spec, extra_label="Allauth")
    OUTPUT_PATH.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(merged['paths'])} paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
