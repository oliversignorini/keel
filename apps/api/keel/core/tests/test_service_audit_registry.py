"""The audit meta-test (PRD v1.2 §8, "The service registry, specified"):
every public, mutating ``services.py`` callable across the whole backend
must be decorated ``@audited`` or ``@not_audited(reason=...)``.

The mechanism is proven directly first — against a deliberately
undecorated fixture function — the same way
``test_ninja_tenant_isolation.py`` proves ``assert_cross_org_404`` against
a deliberately leaky fixture resource before trusting it to walk real
code.
"""

from typing import Any

import pytest

from keel.core import audit
from keel.core.tests.service_audit_registry import (
    ACTORLESS_AUDITED_SERVICES,
    find_audited_services_without_actor,
    find_undecorated_services,
    iter_not_audited_reasons,
    iter_public_mutating_callables,
    iter_service_modules,
)

pytestmark = pytest.mark.django_db


# --- The mechanism, proven directly -------------------------------------


class _FixtureUndecoratedModule:
    __name__ = "keel.core.tests.test_service_audit_registry._fixture_undecorated"


def _undecorated_mutating_service(*, actor: Any = None) -> None:
    """Looks exactly like a real, forgotten service: public, no
    underscore, no decorator."""


def _fixture_module_with_a_gap() -> Any:
    module = _FixtureUndecoratedModule()
    _undecorated_mutating_service.__module__ = module.__name__
    module.leaky_service = _undecorated_mutating_service  # type: ignore[attr-defined]
    return module


def test_iter_public_mutating_callables_finds_an_undecorated_function() -> None:
    module = _fixture_module_with_a_gap()

    found = list(iter_public_mutating_callables(module))

    assert _undecorated_mutating_service in found


def test_a_deliberately_undecorated_service_is_reported_as_a_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proof this meta-test actually catches something: point
    ``iter_service_modules`` at a module containing one undecorated
    function and assert it is reported — the exact shape of the real
    gap this meta-test exists to prevent."""
    module = _fixture_module_with_a_gap()
    monkeypatch.setattr(
        "keel.core.tests.service_audit_registry.iter_service_modules", lambda: iter([module])
    )

    gaps = find_undecorated_services()

    assert gaps == [f"{module.__name__}.{_undecorated_mutating_service.__qualname__}"]


def test_a_decorated_service_is_not_reported_as_a_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    def well_behaved_service(*, actor: Any = None) -> None:
        pass

    module = _FixtureUndecoratedModule()
    # __module__ must be set *before* decorating: the registry key is
    # computed from __module__/__qualname__ at decoration time, and
    # iter_public_mutating_callables's lookup uses whatever they are now
    # — the two must match, same as the real functions this mirrors.
    well_behaved_service.__module__ = module.__name__
    well_behaved_service = audit.not_audited("fixture — this one is fine")(well_behaved_service)
    module.fine_service = well_behaved_service  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "keel.core.tests.service_audit_registry.iter_service_modules", lambda: iter([module])
    )

    assert find_undecorated_services() == []


# --- The real meta-test: walks every services.py in the backend --------


def test_every_public_mutating_service_is_audited_or_justified() -> None:
    """The failing-then-passing criterion ("Demonstrate it failing"): this
    test fails, by name, listing every gap, the moment any ``services.py``
    gains a public mutating function with neither marker."""
    gaps = find_undecorated_services()

    assert not gaps, (
        "The following public services.py callables are decorated with "
        "neither @audited nor @not_audited(reason=...) (PRD v1.2 §8): "
        f"{gaps}. Add one or the other — an @not_audited reason is a valid "
        "answer, a silent gap is not."
    )


def test_at_least_one_services_module_was_actually_walked() -> None:
    """A meta-test that silently walks zero modules is as vacuous as one
    that never fails — this guards against ``iter_service_modules``
    breaking (a bad glob, a renamed ``keel`` package) and the meta-test
    above passing for the wrong reason."""
    assert len(list(iter_service_modules())) >= 5


def test_iter_not_audited_reasons_finds_real_production_reasons() -> None:
    """Every ``@not_audited`` reason actually used in the codebase today
    is non-empty — the same "an exemption you have to write a paragraph
    for" requirement PRD §4 invariant 7 puts on ``GLOBAL_JUSTIFICATION``."""
    reasons = list(iter_not_audited_reasons())

    assert reasons, "expected at least one real @not_audited(reason=...) in the codebase"
    blank = [name for name, reason in reasons if not (reason or "").strip()]
    assert not blank, f"the following @not_audited entries have a blank reason: {blank}"


# --- The actor contract -------------------------------------------------


def test_every_audited_service_takes_an_actor() -> None:
    """``@audited`` reads the actor out of ``kwargs["actor"]``. A service
    that calls the same person something else — ``created_by``,
    ``invited_by``, ``user`` — silently writes every one of its rows with
    ``actor=NULL``, which no call site or row inspection reveals. A
    deliberate exception goes in ``ACTORLESS_AUDITED_SERVICES`` with its
    reason."""
    gaps = find_audited_services_without_actor()

    assert not gaps, (
        "The following @audited services have no `actor` parameter, so every "
        f"audit row they write has actor=NULL: {gaps}. Rename the parameter to "
        "`actor` (the model field it lands in can keep its own name), or add it "
        "to ACTORLESS_AUDITED_SERVICES with a reason."
    )


def test_the_actorless_allowlist_entries_are_real_and_reasoned() -> None:
    """An allowlist entry naming a function that no longer exists silently
    exempts nothing — and would keep exempting it after a rename."""
    audited_keys = {key for key, entry in audit.registry if entry["kind"] == "audited"}

    assert ACTORLESS_AUDITED_SERVICES, "expected at least one documented actorless service"
    stale = [key for key in ACTORLESS_AUDITED_SERVICES if key not in audited_keys]
    assert not stale, f"ACTORLESS_AUDITED_SERVICES names non-@audited functions: {stale}"
    blank = [key for key, reason in ACTORLESS_AUDITED_SERVICES.items() if not reason.strip()]
    assert not blank, f"the following actorless exemptions have a blank reason: {blank}"
