"""CLAUDE.md invariant 7, asserted for this app specifically: every
public callable in ``services.py`` is registered as ``@audited`` or
``@not_audited``.

``keel/audit`` already runs a repo-wide version of this walk. This
narrower copy ships with the app on purpose — it fails naming *this*
module the moment someone adds an undecorated service here, instead of
failing in a shared meta-test whose output names a file the author may
not be looking at. It is also the test that keeps the invariant with the
app if the app is ever moved out of this repo.
"""

import inspect

from keel.__app__ import services
from keel.core.audit import registry


def test_every_mutating_service_is_audited_or_explicitly_not_audited() -> None:
    registered = {key for key, _entry in registry}

    undecorated = []
    for name, func in inspect.getmembers(services, inspect.isfunction):
        if func.__module__ != services.__name__:
            continue
        # Private helpers are not the service surface — same rule the
        # repo-wide walk in keel/core/tests/service_audit_registry.py
        # applies. A `_dispatch_x` that only enqueues a task has no effect
        # of its own to record; the audited service that calls it does.
        if name.startswith("_"):
            continue
        key = f"{func.__module__}.{func.__qualname__}"
        # The @audited wrapper registers under the *wrapped* function's
        # qualname, which functools.wraps preserves — so a decorated
        # service and an undecorated one are told apart by registry
        # membership, not by inspecting the object.
        if key in registered:
            continue
        undecorated.append(name)

    assert not undecorated, (
        f"services in keel.__app__.services carry neither @audited nor "
        f"@not_audited(reason=...): {sorted(undecorated)}"
    )


def test_every_audited_service_names_its_actor_parameter_actor() -> None:
    """``keel.core.audit``'s wrapper reads the actor out of the call's
    ``actor`` kwarg and nowhere else — a service that names the same
    person after the model field it lands in (``created_by``) writes
    every one of its audit rows with ``actor=NULL``, invisibly. The
    repo-wide version of this walk lives in
    ``keel/core/tests/service_audit_registry.py``."""
    entries = {key: entry for key, entry in registry}

    missing = []
    for name, func in inspect.getmembers(services, inspect.isfunction):
        if func.__module__ != services.__name__ or name.startswith("_"):
            continue
        entry = entries.get(f"{func.__module__}.{func.__qualname__}")
        if entry is None or entry["kind"] != "audited":
            continue
        if "actor" not in inspect.signature(entry["func"]).parameters:
            missing.append(name)

    assert not missing, (
        f"@audited services in keel.__app__.services with no `actor` parameter, so "
        f"every audit row they write has actor=NULL: {sorted(missing)}"
    )
