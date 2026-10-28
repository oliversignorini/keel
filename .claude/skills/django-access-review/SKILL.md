---
name: django-access-review
description: 'Django access control and IDOR security review. Use when reviewing Django Ninja resources and routes, selectors, permission guards, ORM queries, or any Python/Django code handling user authorization. Trigger keywords: "IDOR", "access control", "authorization", "Django permissions", "object permissions", "tenant isolation", "broken access".'
allowed-tools: Read Grep Glob Bash Task
source: https://github.com/getsentry/skills/tree/main/skills/django-access-review
source_ref: d18b7aa8ba878354e5c348310230e652f7690f9c
license: LICENSE
license_spdx: Apache-2.0
---

<!--
Reference material based on OWASP Cheat Sheet Series (CC BY-SA 4.0)
https://cheatsheetseries.owasp.org/
-->

# Django Access Control & IDOR Review

Find access control vulnerabilities by investigating how the codebase answers one question:

**Can User A access, modify, or delete User B's data?**

## Philosophy: Investigation Over Pattern Matching

Do NOT scan for predefined vulnerable patterns. Instead:

1. **Understand** how authorization works in THIS codebase
2. **Ask questions** about specific data flows
3. **Trace code** to find where (or if) access checks happen
4. **Report** only what you've confirmed through investigation

Every codebase implements authorization differently. Your job is to understand this specific implementation, then find gaps.

---

## Phase 1: The Authorization Model (already answered)

This is keel. The questions this phase normally asks are settled by AGENTS.md
invariants 2 and 6 and by gates that fail the build, so the answers below are
the starting point — not something to rediscover. Verify them against the
tree, then spend the review on Phase 2 onwards.

### How is authorization enforced?

- **One file holds every rule.** `keel/organizations/permissions.py` — the
  `Perm` code constants, every guard implementation, and `has_perm`
  re-exported so call sites read `permissions.has_perm`.
  `keel/core/authz.py` holds only the `Decision` type
  (`Decision.allow()` / `Decision.deny(reason, details)`), the `Guard`
  protocol and the `PermissionRegistry` — no rules.
- **No DRF.** ADR 0001 replaced DRF with Django Ninja: no
  `permission_classes`, no viewsets, no DRF permission objects. A review
  finding phrased in DRF terms is wrong for this repo.
- **Resources, not mixins.** A route lives on a `GlobalResource` or
  `OrgScopedResource` subclass (`keel/core/authz.py`) and authorizes with
  `resolve_and_authorize(request, org_slug, (Perm.X,))`, which resolves the
  org and checks the codes in one call. `keel/widgets/views.py` is the
  reference shape.
- **Codes only, never roles.** A role name in a conditional is the bug.
  `_members_remove_guard`'s last-owner check keys on `Perm.ORG_TRANSFER` —
  the code only the Owner preset holds — precisely to avoid reading
  `role.name`.
- **Gated.** `scripts/check_permission_lint.py` greps for `Decision.allow(`,
  `Decision.deny(` and `registry.register(` outside the sanctioned file:
  `cd apps/api && uv run python ../../scripts/check_permission_lint.py`.

### How are queries scoped?

- `OrgScopedQuerySet.for_organization(organization)`
  (`keel/core/models.py`) — a plain `.filter(organization=organization)`.
  Every tenant table inherits `OrgScopedModel`.
- Reads live in `selectors.py` and nowhere else (invariant 1). A selector
  that does not start from `for_organization` on a scoped model is a finding.
- Detail fetches go through `get_scoped_or_404(queryset, pk)`
  (`keel/core/selectors.py`): it filters the *already scoped* queryset and
  raises `Http404` on a miss.

### What's the ownership model?

Organization tenancy, with role-derived permission codes inside the org:
`organization` FK on the row, `Membership` on the user side, `Perm.*` codes
granted by role presets (`keel/organizations/roles.py`). There is no
per-row owner check — `created_by` is provenance, not authorization.

### Cross-org access returns 404, not 403

This is invariant 6 and it is deliberate: a 403 on a resource in another org
confirms the row exists. `resolve_and_authorize` raises `Http404` on a
non-member or nonexistent slug, and `get_scoped_or_404` cannot see the row at
all. **A 403 where a 404 belongs is a finding, even though nothing is
"leaked" beyond existence.**

### Every resource declares its scope

`OrgScopedResource.__init_subclass__` fails at import unless the class sets
either `organization_scoped = True` plus `test_factory`, or
`organization_scoped = False` plus `GLOBAL_JUSTIFICATION`. A new
`organization_scoped = False` resource is the highest-value thing to review
in this repo — read its justification and disbelieve it.

### Verify, then review

```bash
cd apps/api && uv run python ../../scripts/check_permission_lint.py
cd apps/api && uv run pytest   keel/organizations/tests/test_meta_router_wiring.py   keel/organizations/tests/test_ninja_tenant_isolation.py
```

`test_meta_router_wiring.py` walks the router so a declared-but-unmounted
resource fails; `test_ninja_tenant_isolation.py` asserts the 404. Both
passing means the *mechanical* guarantees hold — it says nothing about
whether a guard encodes the right rule, which is what this review is for.

**The gaps worth finding here are: a service that reimplements a check
instead of calling `has_perm`; a selector that skips `for_organization`; a
new `GLOBAL_JUSTIFICATION`; a route that 403s where it should 404; and a
`Perm` code checked for the wrong action.**

---

## Phase 2: Map the Attack Surface

Identify endpoints that handle user-specific data:

### What resources exist?

```
□ What models contain user data?
□ Which have ownership fields (owner_id, user_id, organization_id)?
□ Which are accessed via ID in URLs or request bodies?
```

### What operations are exposed?

For each resource, map:
- List endpoints - what data is returned?
- Detail/retrieve endpoints - how is the object fetched?
- Create endpoints - who sets the owner?
- Update endpoints - can users modify others' data?
- Delete endpoints - can users delete others' data?
- Custom actions - what do they access?

---

## Phase 3: Ask Questions and Investigate

For each endpoint that handles user data, ask:

### The Core Question

**"If I'm User A and I know the ID of User B's resource, can I access it?"**

Trace the code to answer this:

```
1. Where does the resource ID enter the system?
   - URL path: /api/documents/{id}/
   - Query param: ?document_id=123
   - Request body: {"document_id": 123}

2. Where is that ID used to fetch data?
   - Find the ORM query or database call

3. Between (1) and (2), what checks exist?
   - Is the query scoped to current user?
   - Is there an explicit ownership check?
   - Is there a permission check on the object?
   - Does a base class or mixin enforce access?

4. If you can't find a check, is there one you missed?
   - Check parent classes
   - Check middleware
   - Check managers
   - Check decorators at URL level
```

### Follow-Up Questions

```
□ For list endpoints: Does the query filter to user's data, or return everything?

□ For create endpoints: Who sets the owner - the server or the request?

□ For bulk operations: Are they scoped to user's data?

□ For related resources: If I can access a document, can I access its comments?
  What if the document belongs to someone else?

□ For tenant/org resources: Can User in Org A access Org B's data by changing
  the org_id in the URL?
```

---

## Phase 4: Trace Specific Flows

Pick a concrete endpoint and trace it completely.

### Example Investigation

```
Endpoint: GET /api/v1/orgs/{org_slug}/documents/{id}/

1. Find the route handling this URL
   → retrieve_document() in keel/documents/views.py

2. Check the resource class it hangs off
   → class DocumentResource(OrgScopedResource)
   → organization_scoped = False, GLOBAL_JUSTIFICATION = "internal tooling"
   → The scoping opt-out is the whole finding — read on

3. Check the authorization call
   → no resolve_and_authorize(...) in the handler, only `request.auth`
   → login is proven; no Perm code is checked

4. Check the selector
   → def list_documents(): return Document.objects.all()
   → no for_organization() — returns every org's rows

5. Check the detail fetch
   → Document.objects.get(pk=id), not get_scoped_or_404(...)
   → raises 403/500 rather than the 404 invariant 6 requires

6. Check retrieve() method
   → Uses default, which calls get_object()
   → get_object() uses get_queryset(), which returns all

7. Conclusion: IDOR - Any authenticated user can access any document
```

### What to look for when tracing

```
Potential gap indicators (investigate further, don't auto-flag):
- get_queryset() returns .all() or filters without user
- Direct Model.objects.get(pk=pk) without ownership in query
- ID comes from request body for sensitive operations
- Permission class checks auth but not ownership
- No has_object_permission() and queryset isn't scoped

Likely safe patterns (but verify the implementation):
- get_queryset() filters by request.user or user's org
- Custom permission class with has_object_permission()
- Base class that enforces scoping
- Manager that auto-filters
```

---

## Phase 5: Report Findings

Only report issues you've confirmed through investigation.

### Confidence Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **HIGH** | Traced the flow, confirmed no check exists | Report with evidence |
| **MEDIUM** | Check may exist but couldn't confirm | Note for manual verification |
| **LOW** | Theoretical, likely mitigated | Do not report |

### Suggested Fixes Must Enforce, Not Document

**Bad fix**: Adding a comment saying "caller must validate permissions"
**Good fix**: Adding code that actually validates permissions

A comment or docstring does not enforce authorization. Your suggested fix must include actual code that:
- Validates the user has permission before proceeding
- Raises an exception or returns an error if unauthorized
- Makes unauthorized access impossible, not just discouraged

Example of a BAD fix suggestion:
```python
def get_resource(resource_id):
    # IMPORTANT: Caller must ensure user has access to this resource
    return Resource.objects.get(pk=resource_id)
```

Example of a GOOD fix suggestion:
```python
def get_resource(resource_id, user):
    resource = Resource.objects.get(pk=resource_id)
    if resource.owner_id != user.id:
        raise PermissionDenied("Access denied")
    return resource
```

If you can't determine the right enforcement mechanism, say so - but never suggest documentation as the fix.

### Report Format

```markdown
## Access Control Review: [Component]

### Authorization Model
[Brief description of how this codebase handles authorization]

### Findings

#### [IDOR-001] [Title] (Severity: High/Medium)
- **Location**: `path/to/file.py:123`
- **Confidence**: High - confirmed through code tracing
- **The Question**: Can User A access User B's documents?
- **Investigation**:
  1. Traced GET /api/v1/orgs/{org_slug}/documents/{id}/ to retrieve_document()
  2. Checked the selector - returns Document.objects.all(), no for_organization()
  3. Checked the handler - no resolve_and_authorize(), no Perm code checked
  4. Checked the detail fetch - .get(pk=...), not get_scoped_or_404()
  5. Confirmed the resource opts out via GLOBAL_JUSTIFICATION, so the
     tenant-isolation meta-test never walks it
- **Evidence**: [Code snippet showing the gap]
- **Impact**: Any authenticated user can read any document by ID
- **Suggested Fix**: [Code that enforces authorization - NOT a comment]

### Needs Manual Verification
[Issues where authorization exists but couldn't confirm effectiveness]

### Areas Not Reviewed
[Endpoints or flows not covered in this review]
```

---

## Common Django Authorization Patterns

These are patterns you might find - not a checklist to match against.

### Query Scoping — `selectors.py` only
```python
# The sanctioned shape
Document.objects.for_organization(organization)      # OrgScopedQuerySet

# Equivalent, but written out — fine, just louder
Document.objects.filter(organization=organization)

# Findings
Document.objects.all()                               # unscoped
Document.objects.filter(created_by=request.auth)     # created_by is
                                                     # provenance, not authz
```

### Permission Enforcement — `resolve_and_authorize` / `has_perm`
```python
# In a route: resolve the org and check the codes in one call
organization = resolve_and_authorize(request, org_slug, (Perm.DOCUMENTS_VIEW,))

# In a service: ask, never reimplement
decision = permissions.has_perm(actor, organization, Perm.DOCUMENTS_MANAGE)
if not decision.allowed:
    ...

# Findings
if membership.role.name == "owner":          # role name in a conditional
if actor.id == document.created_by_id:       # hand-rolled ownership check
Decision.deny("nope")                        # a rule outside
                                             # organizations/permissions.py
```

### Detail Fetch — 404, never 403
```python
# Safe: filters the already-scoped queryset, Http404 on a miss
return get_scoped_or_404(selectors.list_documents(organization), id)

# Findings
Document.objects.get(pk=id)                  # unscoped, and wrong status
if doc.organization != organization:         # 403 confirms existence
    raise PermissionDenied()
```

### Ownership Assignment
```python
# Safe: the org comes from the authorized path, the actor from the request
services.create_document(organization=organization, actor=request.auth, ...)

# Findings
services.create_document(**payload.dict())   # does the payload carry
                                             # organization or actor?
```

---

## Investigation Checklist

Use this to guide your review, not as a pass/fail checklist:

```
□ I understand how authorization is typically implemented in this codebase
□ I've identified the ownership model (user, org, tenant, etc.)
□ I've mapped the key endpoints that handle user data
□ For each sensitive endpoint, I've traced the flow and asked:
  - Where does the ID come from?
  - Where is data fetched?
  - What checks exist between input and data access?
□ I've verified my findings by checking parent classes and middleware
□ I've only reported issues I've confirmed through investigation
```
