"""Deny-by-default, proven (PRD §4 task 1.12) — the gate
``keel.core.ninja_auth``'s module docstring promises.

Every router mounted on the shared ``KeelAPI`` instance must declare its
auth explicitly through one of the three sanctioned constructors in
``keel.core.ninja_authz`` (``keel_router`` / ``optional_auth_router`` /
``public_router``). Ninja's own default for a bare ``Router()`` is *no
auth at all* — the sentinel ``ninja.constants.NOT_SET``, distinct from an
explicit ``auth=None`` — so a router that forgot to declare anything would
resolve to a fully open endpoint with nothing in the codebase saying so.
This test walks the real, mounted routers (forcing ``config.urls`` to
import first, same as ``ninja_tenant_isolation.py``'s registry walk) and
fails on the first one that isn't using a sanctioned auth value.
"""

from ninja.constants import NOT_SET

from keel.core.ninja_auth import optional_session_auth, session_auth

_SANCTIONED_AUTH = (session_auth, optional_session_auth, None)


def _mounted_routers() -> list[tuple[str, object]]:
    # Force the URLconf to load (and with it, every app's ninja_api.add_router
    # call) without keel.core importing keel.organizations et al. directly —
    # keel.core must not import keel.organizations (import-linter contract,
    # apps/api/pyproject.toml), and a bare `import config.urls` here would.
    # get_resolver().url_patterns triggers the same load lazily through
    # Django's own machinery instead, the same trick
    # organizations/tests/test_meta_router_wiring.py uses.
    from django.urls import get_resolver

    _ = get_resolver().url_patterns
    from keel.core.ninja_api import api

    return list(api._routers)


def test_every_mounted_router_declares_a_sanctioned_auth() -> None:
    routers = _mounted_routers()
    assert routers, "No routers are mounted — config.urls failed to import routes."

    for path, router in routers:
        if not router.path_operations:
            # NinjaAPI's own unused default_router (main.py:120-121) — no
            # app ever registers an operation on it directly, so there is
            # nothing here for deny-by-default to protect.
            continue
        assert router.auth is not NOT_SET, (
            f"Router mounted at {path!r} never declared an auth value — it "
            "was built with a bare ninja.Router() instead of one of "
            "keel.core.ninja_authz's keel_router() / optional_auth_router() "
            "/ public_router(), so Ninja silently treats every operation on "
            "it as open."
        )
        assert router.auth in _SANCTIONED_AUTH, (
            f"Router mounted at {path!r} declares auth={router.auth!r}, which "
            "is none of the three sanctioned callables (session_auth, "
            "optional_session_auth, or explicit None via public_router()). "
            "Build it with one of keel.core.ninja_authz's router "
            "constructors instead."
        )


def test_every_operation_resolves_to_a_sanctioned_auth_callback() -> None:
    """Belt and braces: an operation-level auth override (bypassing the
    router's own declaration) would slip past the router-level check
    above. None of today's operations set one — this proves that stays
    true, at the granularity that actually runs at request time."""
    for _path, router in _mounted_routers():
        for _url, path_view in router.path_operations.items():
            for operation in path_view.operations:
                callbacks = list(operation.auth_callbacks)
                assert all(callback in _SANCTIONED_AUTH for callback in callbacks), (
                    f"{operation.operation_id!r} resolves to an auth callback "
                    f"outside the sanctioned set: {callbacks!r}."
                )
