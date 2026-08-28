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
