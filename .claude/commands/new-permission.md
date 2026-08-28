Add a permission code for `$ARGUMENTS` (a `resource.action` style name,
e.g. `invoices.approve`).

## 1. Run the generator

```
pnpm gen permission invoices.approve
```

This splices all four places a code has to exist to be real: the
`Perm.<CODE>` constant, `registry.register(...)` with a role-only guard,
the right preset in `roles.py`'s `_MEMBER_CODES`, and the allow/deny pair
in `organizations/tests/test_permissions.py`'s guard table — all
idempotent, so re-running it is a no-op if the code is already fully
wired. **Do not** add a permission check anywhere else by hand; that is
what invariant 2 and `check_permission_lint.py` exist to catch.

## 2. Do the judgement work

- If this permission's rule depends on the _object_, not just the actor's
  role (e.g. "can only approve invoices under $X", or a last-owner style
  guard), replace the generated `_role_guard(Perm.<CODE>)` registration
  with a subject-aware guard — `templates/permission/subject_guard.py` is
  the shape to copy: takes `(user, organization, subject=None)`, returns
  `Decision.allow()` or `Decision.deny(reason, details=...)` with a
  specific machine-readable `reason`, never a bare `Decision.deny("no")`.
- Check by hand whether the generator put the code in the right preset —
  it always adds to `_MEMBER_CODES`; if this code should be Admin/Owner-
  only instead, move it.
- Wire it onto whatever route(s) need it (`_ACTION_PERMISSIONS`).

## 3. Tests (mandatory — invariant 2's CI meta-test fails without both)

The generator adds the code to the guard test table with a role-only
guard already covered by an allow/deny pair. If you replaced it with a
subject-aware guard in step 2, add matching allow/deny cases for the new
guard by hand (in `organizations/tests/guard_cases.py` or wherever this
project's guard test cases live), asserting the specific `reason` string
— not just that `allowed is False`. Run
`cd apps/api && uv run pytest keel/organizations/tests/test_meta_guard_coverage.py -v`
to confirm the registry meta-test sees both cases.

## Finish

`/check-invariants` step 2 and step 4 (permission lint, tenant scoping)
should both be re-run if this permission gates a viewset action.
