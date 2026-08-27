Add a permission code for `$ARGUMENTS` (a `resource.action` style name,
e.g. `invoices.approve`). This touches exactly one file's logic —
`apps/api/keel/organizations/permissions.py` — plus its registrations.
**Do not** add a permission check anywhere else; that is what invariant 2
and `check_permission_lint.py` exist to catch.

1. Add the code as a `Perm.<NAME>` class attribute, next to the
   resource's existing codes if there are any.
2. Decide the guard:
   - **Role-only** (most permissions): `_role_guard(Perm.<NAME>)` — the
     same one-liner every existing code uses.
   - **Subject-aware** (the check depends on the object, not just the
     role — e.g. "can only approve invoices under $X" or a last-owner
     style guard): write a dedicated guard function following
     `_members_remove_guard`'s shape — takes `(user, organization,
subject=None)`, returns a `Decision.allow()` or
     `Decision.deny(reason, details=...)` with a specific machine-
     readable `reason`, never a bare `Decision.deny("no")`.
3. `registry.register(Perm.<NAME>, <guard>)` next to the other
   registrations.
4. Add the code to the right preset's code set in `roles.py`
   (`_MEMBER_CODES`, or the Admin/Owner equivalents) — a code nobody's
   role includes is unreachable and the meta-tests won't catch that, so
   check by hand which preset should get it.
5. Wire it onto whatever viewset(s) need it — `required_permissions` /
   `_ACTION_PERMISSIONS`.

## Tests (mandatory — invariant 2's CI meta-test fails without both)

In `organizations/tests/guard_cases.py` (or wherever the existing guard
test cases live), add:

- One **allow** case: the right role, granted.
- One **deny** case: wrong role, denied, asserting the specific `reason`
  string — not just that `allowed is False`.

Run `cd apps/api && uv run pytest keel/organizations/tests/test_meta_guard_coverage.py -v`
to confirm the registry meta-test now sees both cases for this code.

## Finish

`/check-invariants` step 2 and step 4 (permission lint, tenant scoping)
should both be re-run if this permission gates a viewset action.
