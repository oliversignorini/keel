"""Meta-test 1 (PRD §4 invariant 2): every registered
guard has both an allow test and a deny test, and the deny test asserts
the ``reason``.

Scoped to ``Perm``'s own codes rather than the raw
``keel.core.authz.registry`` — that registry is a process-global
singleton, and ``keel/core/tests/test_authz.py`` permanently registers
several ``fixture.*`` codes into it for its own purposes with no
teardown. Walking the raw registry makes this meta-test's outcome depend
on which other test modules pytest happened to import first in the same
process — exactly the fragility PRD invariant 2's meta-test must not
have. ``Perm``'s attributes are the actual codes this app is responsible
for, and every one of them is asserted to be both registered and covered.

Order independence: ``ALLOW_CASES`` / ``DENY_CASES`` are populated by
decorators evaluated at module *import* time, which for pytest happens
during collection — before any test in the session runs, regardless of
file name or execution order. The explicit import below is a defensive
belt for running this file in isolation.

The "assert the reason" half of PRD invariant 2 is not merely checked
here — it is structural: ``test_permissions.py``'s single
``test_guard_deny`` runner asserts ``decision.reason == case.reason`` for
every entry in ``DENY_CASES``, so a deny case cannot be declared without
that assertion executing.
"""

import keel.organizations.tests.test_permissions  # noqa: F401  (forces case registration)
from keel.core.authz import registry
from keel.organizations.permissions import Perm
from keel.organizations.tests.guard_cases import ALLOW_CASES, DENY_CASES


def _perm_codes() -> list[str]:
    return sorted({value for name, value in vars(Perm).items() if not name.startswith("_")})


def test_every_perm_code_has_a_guard_registered() -> None:
    codes = _perm_codes()
    registered = {code for code, _guard in registry}

    missing = sorted(code for code in codes if code not in registered)

    assert not missing, f"Perm code(s) declared but never registry.register()ed: {missing}"


def test_every_perm_code_has_an_allow_case_declared() -> None:
    codes = _perm_codes()
    allow_codes = {case.code for case in ALLOW_CASES}

    missing = sorted(code for code in codes if code not in allow_codes)

    assert not missing, (
        f"{len(missing)} Perm code(s) have no @allow_case in "
        f"test_permissions.py (PRD §4 invariant 2): {missing}"
    )


def test_every_perm_code_has_a_deny_case_declared() -> None:
    codes = _perm_codes()
    deny_codes = {case.code for case in DENY_CASES}

    missing = sorted(code for code in codes if code not in deny_codes)

    assert not missing, (
        f"{len(missing)} Perm code(s) have no @deny_case in "
        f"test_permissions.py (PRD §4 invariant 2): {missing}"
    )


def test_perm_has_at_least_one_code() -> None:
    """A vacuous pass (zero codes) would make the checks above meaningless
    — guard against that directly."""
    assert len(_perm_codes()) > 0
