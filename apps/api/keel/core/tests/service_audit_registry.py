"""The audit meta-test mechanism (PRD v1.2 §8, "The service registry,
specified"). See
``test_service_audit_registry.py`` for the meta-test itself and the proof
that this mechanism actually catches a gap.

Walks every ``keel/<app>/services.py`` module, collects its public
top-level callables — the mutating ones, per PRD §2 "services mutate and
return; selectors query and return" — and reports any that carry neither
``@audited`` nor ``@not_audited(reason=...)`` in
``keel.core.audit.registry``.

A "public top-level callable" is a function *defined in* the module
(``__module__`` matches, so an imported helper like ``check_limit`` is
never mistaken for one of the module's own services) whose name doesn't
start with ``_`` (private helpers — e.g.
``organizations.services._sync_stripe_customer`` — are deliberately
un-auditable seams, not public services, and are excluded the same way
Python itself treats a leading underscore as "not part of the public
surface").
"""

import importlib
import inspect
import pathlib
from collections.abc import Iterator
from typing import Any

import keel
from keel.core import audit

_KEEL_ROOT = pathlib.Path(keel.__file__).resolve().parent


def iter_service_modules() -> Iterator[Any]:
    """Every ``keel/<app>/services.py``, imported, in a stable (sorted)
    order — walking the filesystem rather than ``INSTALLED_APPS`` means a
    ``services.py`` is covered the moment it exists, before anyone
    remembers to register a viewset for it."""
    for path in sorted(_KEEL_ROOT.glob("*/services.py")):
        app_name = path.parent.name
        yield importlib.import_module(f"keel.{app_name}.services")


def iter_public_mutating_callables(module: Any) -> Iterator[Any]:
    """Public, module-defined, top-level functions — the candidates the
    meta-test requires to be ``@audited`` or ``@not_audited(reason=...)``."""
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("_"):
            continue
        if obj.__module__ != module.__name__:
            continue  # imported, not defined here — not this module's service
        yield obj


def find_undecorated_services() -> list[str]:
    """Qualified names (``module.function``) of every public mutating
    service that is registered in neither
    ``keel.core.audit.registry``'s ``audited`` nor ``not_audited``
    entries — the meta-test's failure list."""
    gaps = []
    for module in iter_service_modules():
        for func in iter_public_mutating_callables(module):
            try:
                audit.registry.get(func)
            except KeyError:
                gaps.append(f"{module.__name__}.{func.__qualname__}")
    return gaps


def iter_not_audited_reasons() -> Iterator[tuple[str, str]]:
    """``(qualified name, reason)`` for every production ``@not_audited``
    entry in the registry — CI prints these on the same principle as
    ``GLOBAL_JUSTIFICATION`` (PRD §4 invariant 7): an escape hatch that
    costs a sentence and appears in every run is a decision; a silent
    exemption is where drift hides. Test-fixture entries (registered
    under a ``tests`` module) are excluded, the same way
    ``iter_global_justifications`` excludes fixture viewsets."""
    for key, entry in audit.registry:
        if entry["kind"] != "not_audited":
            continue
        if "tests" in key.split("."):
            continue
        yield key, entry["reason"]
