# Phase 3 — Organisations, members, permissions

**Source of truth:** `keel-prd.md` v1.2 — §4 "Tenancy and permissions", invariant 2, invariant 7 (both meta-tests), §6 "Invitation" and "Permission denial", §7 organisation/member/role endpoints, §8 Phase 3.
**Depends on:** Phase 1 merged. Phase 2 is concurrent and does not block this.
**Size:** Large. The PRD calls it *"the most consequential phase — everything downstream assumes it is correct."*

---

## Three worktrees, in this order

| Worktree | Owns | Starts |
|---|---|---|
| **`p3-perms`** | `organizations/permissions.py`, the resolver, the two CI meta-tests | Immediately — concurrent with the Phase 2 worktrees |
| **`p3-orgs-api`** | Services, selectors, serializers, viewsets, `/me` | After `p3-perms` merges |
| **`p3-orgs-web`** | `<OrgSwitcher>`, settings General/Members/Roles, `<Can>`, `/onboarding`, `/invite/[token]` | After `p3-orgs-api` merges |

`p3-perms` is separated because everything else in the phase declares `required_permissions` against codes it defines. Landing it first means the other two build against a fixed vocabulary rather than inventing codes that later collide.

**No worktree writes migrations.** `Organization`, `Role`, `Membership` and `Invitation` exist from Phase 1.

---

## What Phase 1 already built, so you do not rebuild it

Read `keel/core/authz.py` before writing anything. It already provides:

- `Decision` — frozen dataclass, `Decision.allow()` / `Decision.deny(reason, details)`
- The `Guard` protocol and the registry, with a stable iteration surface
- `has_perm(user, organization, code, subject=None) -> Decision`, raising `UnregisteredPermissionCode` on a typo
- `HasOrgPermission` — maps a denial to a 403 whose envelope `code` is `Decision.reason`
- `OrgScopedViewSet` / `GlobalViewSet`, with import-time checks for `required_permissions`, `organization_scoped` / `GLOBAL_JUSTIFICATION`, and `test_factory`

**The seam you must fill:** `settings.KEEL_ORGANIZATION_RESOLVER`, a dotted path to a callable `(request, org_slug: str) -> Organization | None`. `keel/core` cannot import `keel.organizations`, which is why this exists. Returning `None` must mean *both* "no such slug" and "you are not an active member" — the same outcome deliberately, because distinguishing them tells an outsider the organisation exists. Phase 1's docstring explains this; do not weaken it.

---

# Worktree A — `p3-perms`

### A.1 — The registry

`organizations/permissions.py`. The `Perm` code constants exactly as PRD §4 lists them, plus a guard registered for each.

- Simple codes are guards that only look at the role. Codes that inspect a subject are registered the same way and declared on a viewset the same way — **the distinction is implementation depth, not category** (PRD invariant 2).
- Re-export `has_perm` from this module so call sites read as the PRD describes them.
- **Only permission codes are ever checked in code. A role name must never appear in a conditional.** Grep for it in your own output before you claim done.

### A.2 — At least one subject-inspecting guard

PRD Phase 3 acceptance requires a guard that inspects a subject, not only the role, registered and declared like any other. Write a real one and make it plausible — the point is proving the shape works, and a fake one proves nothing. `Decision.deny("...", details={...})` must carry something a client could act on.

### A.3 — The resolver

Implement the callable and point `KEEL_ORGANIZATION_RESOLVER` at it. Active membership only — a suspended member resolves to `None`. Test both the missing-slug and the not-a-member path and assert they are indistinguishable from outside.

### A.4 — Preset roles

Owner holds every code. Admin holds everything except `org.delete` and `org.transfer`. Member holds the view codes plus resource CRUD. Seeded on organisation creation — the seeding *function* lives here; `p3-orgs-api` calls it inside the atomic create.

Custom roles behind a feature flag, **off by default**. `Role` and `roles.manage` exist regardless.

### A.5 — The two CI meta-tests

This is the real deliverable of this worktree, and the part most likely to pass while proving nothing.

**Meta-test 1 — every guard is tested.** Walks the registry. Fails if any registered code lacks both an allow test and a deny test. **The deny test must assert the `reason`, not merely that access was refused** — PRD invariant 7 is explicit that a guard denying for the wrong reason passes a boolean test and fails a user. Make the meta-test verify that the assertion on `reason` exists, not just that a deny test exists.

**Meta-test 2 — tenant isolation.** Walks every viewset in the router. For each with `organization_scoped = True`, imports its `test_factory` by dotted path, builds a row in each of two organisations, and asserts every detail route returns **404, not 403**, for a member of the other. Prints every `GLOBAL_JUSTIFICATION` in the CI output.

Both meta-tests must be **demonstrated to fail**: register a guard with no deny test and show the failure; add a scoped viewset that leaks across tenants and show the failure. A meta-test that has never failed is a meta-test that does not work. Paste both.

### A.6 — The lint rule

`grep` for permission checks outside `permissions.py` must return nothing, enforced as a CI lint rule. Show it catching a deliberately misplaced check.

---

# Worktree B — `p3-orgs-api`

### B.1 — Services

`organizations/services.py`. All writes. One `transaction.atomic()` per service function, opened in the service, never in the view. Decorate mutating services `@audited` or `@not_audited(reason=...)` — Phase 1 built both.

- **Create organisation** — atomic: org, Owner membership, three preset roles. All or nothing. Stripe customer creation via `transaction.on_commit()`, never inline.
- **Invitation lifecycle** — create with a signed token and 7-day expiry; revoke; accept. Accepting is atomic: membership created, `accepted_at` set. Seat sync on commit, behind `BILLING_SEAT_PRICING` (Phase 4 owns the sync itself — leave the hook and note the dependency).
- **Membership** — change role, remove. **The last Owner cannot be removed or demoted.**
- Transfer ownership, delete organisation.

**Services may call guards; services may never reimplement them.** If a service needs a check it calls `has_perm` and raises on denial. A service enforcing a rule authorization already owns is a second source of truth and the two will diverge.

### B.2 — Selectors

`organizations/selectors.py`. All reads. Services mutate and return; selectors query and return.

### B.3 — Viewsets and serializers

Per PRD §7. Every viewset declares `required_permissions`, `organization_scoped` or a real `GLOBAL_JUSTIFICATION`, and `test_factory` when scoped.

`GET /api/v1/permissions/` returns the registry for the role editor — global, so it needs a justification.

`GET /api/v1/me/` returns user, organisations, current role, **resolved permission code list**, and resolved entitlements. Entitlement resolution is Phase 4's; leave the seam and coordinate rather than duplicating it. This single endpoint is what the client renders from.

### B.4 — Invitation edge cases

From PRD §6, all four distinct and all tested:

- Wrong email → rejected **without disclosing the invitee**
- Expired and revoked → **indistinguishable to the recipient**
- Not signed in → signup with prefilled, locked email, then re-resolve
- Signed in, email matches → accept

---

# Worktree C — `p3-orgs-web`

- `<OrgSwitcher>` — dropdown with create-new. Immediately after the logo; tenant context always visible.
- `/onboarding` — create first organisation.
- `/invite/[token]` — all four outcomes above, with copy that does not leak.
- `/app/[org]/settings/general`, `/members`, `/roles`. Secondary horizontal tab row, not a nested sidebar.
- `<Can>` — renders children only when the user holds a code. **Presentation only.** Removing it client-side must still yield 403 from the API, and there is a test for exactly that.
- Switching organisation updates the route and refetches all data.

---

## Acceptance — evidence required

From PRD §8 Phase 3:

- [ ] Creating an organisation is atomic: org, Owner membership, three preset roles, all or nothing
- [ ] Every registered guard has both an allow and a deny test, and the deny test asserts the `reason`
- [ ] **Meta-test 1 fails CI if any registered guard lacks both tests — demonstrated failing**
- [ ] A denial reaches the client as a 403 whose `code` is the `Decision.reason`, verified end to end for one role denial and one state denial
- [ ] A guard that inspects a subject exists, is registered like any other, and is declared on a viewset the same way
- [ ] **Meta-test 2 walks every viewset, asserts cross-org access returns 404 for scoped ones, prints every `GLOBAL_JUSTIFICATION` — demonstrated failing on a deliberately leaky viewset**
- [ ] `grep` for permission checks outside `permissions.py` returns nothing; the CI lint rule catches a deliberate violation
- [ ] No role name appears in any conditional
- [ ] Invitation accepted by the wrong email is rejected without disclosing the invitee
- [ ] Expired and revoked invitations are indistinguishable to the recipient
- [ ] The last Owner cannot be removed or demoted
- [ ] `<Can>` hides actions; removing it client-side still yields 403 from the API
- [ ] A non-member and a nonexistent slug are indistinguishable from outside
- [ ] Custom roles off by default; enabling is a settings change, not a migration
- [ ] No migrations were generated

---

## How to work

- Strict TDD on the API worktrees. Tests alongside on the web worktree, using `mattpocock-skills:tdd`.
- **Both meta-tests must be shown failing before they are trusted.** This is the single most important instruction in this document.
- Verify, do not assert. Every box needs pasted output.
- Update the Orca worktree comment at each task boundary.
- Do not push, do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; the pasted output of both meta-tests failing and then passing; the full list of registered codes; anything in the PRD that looked wrong from inside the code.
