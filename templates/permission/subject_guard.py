"""The judgement half of `gen permission`, kept as a real file so it is
lintable and copy-pasteable rather than described in prose.

`gen permission` writes the *mechanical* half itself, and it is four
one-line forms rather than a template — the `Perm` constant, the
`registry.register(...)` call, the preset-role entry in `roles.py`, and
the guard-test-table entry in `test_permissions.py`. Four fixed lines
generated from one code string are not a template; putting them in a file
would be indirection with nothing on the other end of it (packages/cli's
`src/anchors.ts::splicePermission` holds them).

What is *not* mechanical is a subject-aware guard: a check that depends on
the object being acted on, not only on the actor's role. `gen permission`
always emits a role-only guard, because a role-only guard is the correct
default and is what CLAUDE.md invariant 2 calls "a simple code". When the
rule is really "only if the invoice is under $X" or "not the last owner",
copy the shape below into `keel/organizations/permissions.py` — the one
file invariant 2 allows a permission rule to live in — and replace the
generated `_role_guard(...)` registration with it.

Two things this shape is careful about, both of which a hand-written guard
routinely gets wrong:

  * It denies with a *specific, machine-readable* reason, never a bare
    `Decision.deny("no")`. That reason becomes the error envelope's `code`
    on the 403 and is what a client branches on.
  * It re-checks the plain role code first. A subject-aware guard that
    only inspects the subject grants the action to anyone whose role does
    not hold the code at all.
"""

from typing import Any

from keel.core.authz import Decision, Guard, registry
from keel.organizations.permissions import DenialReason, Perm, _resolve_role_permissions


def __resource___approve_guard(
    user: Any, organization: Any, subject: Any | None = None
) -> Decision:
    permissions = _resolve_role_permissions(user, organization)
    if Perm.__RESOURCE___UPDATE not in permissions:
        return Decision.deny(
            DenialReason.INSUFFICIENT_ROLE, details={"required": Perm.__RESOURCE___UPDATE}
        )
    if subject is not None and getattr(subject, "is_locked", False):
        # Replace with the real subject condition. Whatever it is, deny
        # with its own reason code and enough detail for the caller to act
        # on — not with INSUFFICIENT_ROLE, which would say the actor's
        # role is wrong when the actor's role is fine and the object is
        # the problem.
        return Decision.deny("__resource___locked", details={"__resource___id": str(subject.pk)})
    return Decision.allow()


# Registered exactly like a role-only code — the distinction is
# implementation depth, not category (CLAUDE.md invariant 2).
_guard: Guard = __resource___approve_guard
registry.register(Perm.__RESOURCE___UPDATE, _guard)
