---
name: django-perf-review
description: Django performance code review. Use when asked to "review Django performance", "find N+1 queries", "optimize Django", "check queryset performance", "database performance", "Django ORM issues", or audit Django code for performance problems.
allowed-tools: Read Grep Glob Bash Task
source: https://github.com/getsentry/skills/tree/main/skills/django-perf-review
source_ref: d18b7aa8ba878354e5c348310230e652f7690f9c
license: LICENSE
license_spdx: Apache-2.0
---

# Django Performance Review

Review Django code for **validated** performance issues. Research the codebase to confirm issues before reporting. Report only what you can prove.

## Review Approach

1. **Research first** - Trace data flow, check for existing optimizations, verify data volume
2. **Validate before reporting** - Pattern matching is not validation
3. **Zero findings is acceptable** - Don't manufacture issues to appear thorough
4. **Severity must match impact** - If you catch yourself writing "minor" in a CRITICAL finding, it's not critical. Downgrade or skip it.

## Impact Categories

Issues are organized by impact. Focus on CRITICAL and HIGH - these cause real problems at scale.

| Priority | Category | Impact |
|----------|----------|--------|
| 1 | N+1 Queries | **CRITICAL** - Multiplies with data, causes timeouts |
| 2 | Unbounded Querysets | **CRITICAL** - Memory exhaustion, OOM kills |
| 3 | Missing Indexes | **HIGH** - Full table scans on large tables |
| 4 | Write Loops | **HIGH** - Lock contention, slow requests |
| 5 | Inefficient Patterns | **LOW** - Rarely worth reporting |

---

## Priority 1: N+1 Queries (CRITICAL)

**Impact:** Each N+1 adds `O(n)` database round trips. 100 rows = 100 extra queries. 10,000 rows = timeout.

### Rule: Prefetch related data accessed per row

This is an API-only codebase — no templates, no `render()`. The loop is the
serialization of a list response, one `WidgetOut` per row, so it is implicit
and easy to miss.

Validate by tracing: `views.py` route → `selectors.py` queryset →
`schemas.py` resolver / attribute access → per-row query.

```python
# PROBLEM: N+1 — the queryset carries no relation, so every row's
# `created_by` is a separate query when the schema serializes it.
# selectors.py
def list_widgets(organization):
    return Widget.objects.for_organization(organization)

# SOLUTION: select_related in the selector — the only place reads live.
# selectors.py
def list_widgets(organization):
    return Widget.objects.for_organization(organization).select_related("created_by")
```

`keel/widgets/selectors.py` says this out loud: `select_related` there is
not an optimisation, it is the contract `tests/test_query_counts.py` pins —
the list endpoint is one query regardless of row count. A new list selector
without a query-count test is the finding, not just the missing
`select_related`.

### Rule: Annotate in `selectors.py`, resolve in `schemas.py`

A Ninja `Schema` resolver (`resolve_<field>`) is the shape DRF's
`SerializerMethodField` took. It runs once per row, so a query inside one is
an N+1 by construction.

```python
# PROBLEM: the resolver queries per object
# schemas.py
class WidgetOut(KeelSchema):
    order_count: int

    @staticmethod
    def resolve_order_count(obj) -> int:
        return obj.orders.count()  # ← one query per row

# SOLUTION: annotate in the selector; the resolver only reads the attribute
# — or drop the resolver entirely and let the field name match the
# annotation, as `WidgetOut.created_by` does with `created_by_id`.
# selectors.py
def list_widgets(organization):
    return (
        Widget.objects.for_organization(organization)
        .select_related("created_by")
        .annotate(order_count=Count("orders"))
    )

# schemas.py
class WidgetOut(KeelSchema):
    order_count: int
```

Annotating in the view instead of the selector is a second finding — it puts
a read in a layer that may not hold one (invariant 1).

### Rule: Nested output schemas are how a list endpoint becomes an N+1

`keel/widgets/schemas.py` serializes a relation as its id, never as a nested
object, on purpose. A new output schema with a nested sibling schema needs
either `prefetch_related` in the selector *and* a query-count test, or the id
treatment.

### Rule: Model properties that query are dangerous per row

```python
# PROBLEM: Property triggers query when accessed
class Widget(models.Model):
    @property
    def recent_events(self):
        return self.events.filter(created__gte=last_week)[:5]

# Named in an output schema, or read in a resolver = N+1

# SOLUTION: Use Prefetch with custom queryset, or annotate — in the selector
```

### Validation Checklist for N+1
- [ ] Traced data flow from `views.py` through `selectors.py` to `schemas.py`
- [ ] Confirmed the related field is reached once per row (output schema
      field, resolver, or nested schema)
- [ ] Checked whether the slice has a query-count test pinning the count
- [ ] Searched codebase for existing select_related/prefetch_related
- [ ] Verified table has significant row count (1000+)
- [ ] Confirmed this is a hot path (not admin, not rare action)

---

## Priority 2: Unbounded Querysets (CRITICAL)

**Impact:** Loading entire tables exhausts memory. Large tables cause OOM kills and worker restarts.

### Rule: Always paginate list endpoints

There is no `paginate_by` here — pagination is `keel/core/pagination.py`
(cursor-based, `{ results, next, previous }`). A list route declares
`response=Page[<Out>]` so the OpenAPI document and the generated TypeScript
client know the rows are typed, and returns `paginate(request, queryset)`.

```python
# PROBLEM: no pagination — the route returns every row
@router.get("/{org_slug}/widgets/", response=list[WidgetOut], operation_id="listWidgets")
def list_widgets(request, org_slug: str):
    return selectors.list_widgets(organization)

# SOLUTION: the repo's cursor paginator
from keel.core.pagination import Page, paginate

@router.get("/{org_slug}/widgets/", response=Page[WidgetOut], operation_id="listWidgets")
def list_widgets(request, org_slug: str):
    queryset = selectors.list_widgets(organization)
    return paginate(request, queryset)
```

A route returning `list[...]` instead of `Page[...]` is the finding, even if
the table is small today. Do not hand-roll a `?limit=/?offset=` scheme or a
"cursor = last id seen" one: that module's docstring explains why the naive
cursor is subtly wrong across ties, and `keel/core/tests/test_ninja_pagination.py`
pins the behaviour.

### Rule: Use iterator() for large batch processing

```python
# PROBLEM: Loads all objects into memory at once
for user in User.objects.all():
    process(user)

# SOLUTION: Stream with iterator()
for user in User.objects.iterator(chunk_size=1000):
    process(user)
```

### Rule: Never call list() on unbounded querysets

```python
# PROBLEM: Forces full evaluation into memory
all_users = list(User.objects.all())

# SOLUTION: Keep as queryset, slice if needed
users = User.objects.all()[:100]
```

### Validation Checklist for Unbounded Querysets
- [ ] Table is large (10k+ rows) or will grow unbounded
- [ ] Route returns `list[...]` rather than `Page[...]`, or a selector/job iterates without `iterator()` or slicing
- [ ] This runs on user-facing request (not background job with chunking)

---

## Priority 3: Missing Indexes (HIGH)

**Impact:** Full table scans. Negligible on small tables, catastrophic on large ones.

### Rule: Index fields used in WHERE clauses on large tables

```python
# PROBLEM: Filtering on unindexed field
# User.objects.filter(email=email)  # full scan if no index

class User(models.Model):
    email = models.EmailField()  # ← no db_index

# SOLUTION: Add index
class User(models.Model):
    email = models.EmailField(db_index=True)
```

### Rule: Index fields used in ORDER BY on large tables

```python
# PROBLEM: Sorting requires full scan without index
Order.objects.order_by('-created')

# SOLUTION: Index the sort field
class Order(models.Model):
    created = models.DateTimeField(db_index=True)
```

### Rule: Use composite indexes for common query patterns

```python
class Order(models.Model):
    user = models.ForeignKey(User)
    status = models.CharField(max_length=20)
    created = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),  # for filter(user=x, status=y)
            models.Index(fields=['status', '-created']),  # for filter(status=x).order_by('-created')
        ]
```

### Validation Checklist for Missing Indexes
- [ ] Table has 10k+ rows
- [ ] Field is used in filter() or order_by() on hot path
- [ ] Checked model - no db_index=True or Meta.indexes entry
- [ ] Not a foreign key (already indexed automatically)

---

## Priority 4: Write Loops (HIGH)

**Impact:** N database writes instead of 1. Lock contention. Slow requests.

### Rule: Use bulk_create instead of create() in loops

```python
# PROBLEM: N inserts, N round trips
for item in items:
    Model.objects.create(name=item['name'])

# SOLUTION: Single bulk insert
Model.objects.bulk_create([
    Model(name=item['name']) for item in items
])
```

### Rule: Use update() or bulk_update instead of save() in loops

```python
# PROBLEM: N updates
for obj in queryset:
    obj.status = 'done'
    obj.save()

# SOLUTION A: Single UPDATE statement (same value for all)
queryset.update(status='done')

# SOLUTION B: bulk_update (different values)
for obj in objects:
    obj.status = compute_status(obj)
Model.objects.bulk_update(objects, ['status'], batch_size=500)
```

### Rule: Use delete() on queryset, not in loops

```python
# PROBLEM: N deletes
for obj in queryset:
    obj.delete()

# SOLUTION: Single DELETE
queryset.delete()
```

### Validation Checklist for Write Loops
- [ ] Loop iterates over 100+ items (or unbounded)
- [ ] Each iteration calls create(), save(), or delete()
- [ ] This runs on user-facing request (not one-time migration script)

---

## Priority 5: Inefficient Patterns (LOW)

**Rarely worth reporting.** Include only as minor notes if you're already reporting real issues.

### Pattern: count() vs exists()

```python
# Slightly suboptimal
if queryset.count() > 0:
    do_thing()

# Marginally better
if queryset.exists():
    do_thing()
```

**Usually skip** - difference is <1ms in most cases.

### Pattern: len(queryset) vs count()

```python
# Fetches all rows to count
if len(queryset) > 0:  # bad if queryset not yet evaluated

# Single COUNT query
if queryset.count() > 0:
```

**Only flag** if queryset is large and not already evaluated.

### Pattern: get() in small loops

```python
# N queries, but if N is small (< 20), often fine
for id in ids:
    obj = Model.objects.get(id=id)
```

**Only flag** if loop is large or this is in a very hot path.

---

## Validation Requirements

Before reporting ANY issue:

1. **Trace the data flow** - Follow queryset from creation to consumption
2. **Search for existing optimizations** - Grep for select_related, prefetch_related, pagination
3. **Verify data volume** - Check if table is actually large
4. **Confirm hot path** - Trace call sites, verify this runs frequently
5. **Rule out mitigations** - Check for caching, rate limiting

**If you cannot validate all steps, do not report.**

---

## Output Format

```markdown
## Django Performance Review: [File/Component Name]

### Summary
Validated issues: X (Y Critical, Z High)

### Findings

#### [PERF-001] N+1 Query in listWidgets (CRITICAL)
**Location:** `keel/widgets/selectors.py:16`

**Issue:** `WidgetOut.created_by` is reached once per row, but the selector
carries no `select_related` — one extra query per row in the list response.

**Validation:**
- Traced: `views.py` `listWidgets` → `selectors.list_widgets` →
  `schemas.WidgetOut.resolve_created_by`, once per serialized row
- Searched codebase: no `select_related("created_by")` on this queryset
- `widgets` table: 50k+ rows
- Hot path: the org dashboard's first request
- No query-count test pins this route

**Evidence:**
```python
def list_widgets(organization):
    return Widget.objects.for_organization(organization)  # no select_related
```

**Fix:**
```python
def get_queryset(self):
    return User.objects.filter(active=True).select_related('profile')
```
```

If no issues found: "No performance issues identified after reviewing [files] and validating [what you checked]."

**Before submitting, sanity check each finding:**
- Does the severity match the actual impact? ("Minor inefficiency" ≠ CRITICAL)
- Is this a real performance issue or just a style preference?
- Would fixing this measurably improve performance?

If the answer to any is "no" - remove the finding.

---

## What NOT to Report

- Test files
- Admin-only views
- Management commands
- Migration files
- One-time scripts
- Code behind disabled feature flags
- Tables with <1000 rows that won't grow
- Patterns in cold paths (rarely executed code)
- Micro-optimizations (exists vs count, only/defer without evidence)

### False Positives to Avoid

**Queryset variable assignment is not an issue:**
```python
# This is FINE - no performance difference
projects_qs = Project.objects.filter(org=org)
projects = list(projects_qs)

# vs this - identical performance
projects = list(Project.objects.filter(org=org))
```
Querysets are lazy. Assigning to a variable doesn't execute anything.

**Single query patterns are not N+1:**
```python
# This is ONE query, not N+1
projects = list(Project.objects.filter(org=org))
```
N+1 requires a loop that triggers additional queries. A single `list()` call is fine.

**Missing select_related on single object fetch is not N+1:**
```python
# This is 2 queries, not N+1 - report as LOW at most
state = AutofixState.objects.filter(pr_id=pr_id).first()
project_id = state.request.project_id  # second query
```
N+1 requires a loop. A single object doing 2 queries instead of 1 can be reported as LOW if relevant, but never as CRITICAL/HIGH.

**Style preferences are not performance issues:**
If your only suggestion is "combine these two lines" or "rename this variable" - that's style, not performance. Don't report it.
