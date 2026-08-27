# Phase 10 — DRF → Django Ninja

**Source of truth:** `docs/adr/0001-django-ninja-over-drf.md`. Read it first — it contains the inspection, the cost, and the abort condition.
**Depends on:** nothing, but see the exclusion below.
**Size:** Large. Five stages, run **in order, one worktree at a time**.

---

## The exclusion, which matters more than anything else here

While this phase runs, **no other worktree may add or change a view,
serializer, route, permission, or generated-client call site.** Phases 11,
13, 14, 15 and 16 all touch those and are blocked until this merges. Phase
12 (`infra/`, settings, docs) and Phase 9 are the only safe concurrents.

## The success criterion, which is unusual

**Nothing user-visible changes**, except the three things listed below.
Same URLs, same status codes, same error envelope, same cursor-pagination
semantics, same auth behaviour, same invariants enforced with the same
force. If the diff of `openapi.merged.json` shows a route appearing,
disappearing, or changing shape, that is a regression, not progress.

### The three allowed changes

Two of them are the PRD's own outstanding deviations at v1.3, and they are
folded in here deliberately: this phase already regenerates the client and
already sweeps all 41 `apps/web` call sites, so doing them separately means
paying that cost twice.

1. **Operation IDs and component-schema names** change with the generator.
   Unavoidable; stage 10.E propagates them.
2. **`/api/v1/organizations/…` → `/api/v1/orgs/…`.** PRD §7 specifies
   `orgs`; the implementation used the longer form throughout, and v1.3
   records it as a known deviation. Rename it in 10.C, across routes,
   permission codes if they embed the segment, tests, and the frontend.
   Note this is *not* the tenant-noun rewrite — that is `init`'s job in
   Phase 17 and stays parameterised.
3. **`GET /api/v1/plans/` gains the cursor envelope.** It returns a bare
   array today, against §7's convention that all collections are
   cursor-paginated. `PlanViewSet` is a `ListModelMixin` on `GlobalViewSet`;
   it should page like everything else.

Anything beyond those three is a regression.

## The abort condition

If, after stage 10.A and 10.B, the invariant meta-tests cannot be made to
hold with **equal force** — same failure modes caught, demonstrated by
deliberately breaking each one — then stop. Do not weaken an invariant to
fit the framework. Report it, revert, and the ADR gets superseded. That is a
successful outcome for this phase, not a failed one.

---

## Boundary

**In scope:** `apps/api` API layer, `scripts/merge_openapi.py`,
`packages/api-client`, the `@keel/api-client` call sites in `apps/web`, and
CI steps that name DRF.

**Out of scope:**

| Thing | Owner |
|---|---|
| Models, migrations, `services.py`, `selectors.py` business logic | Nobody — do not touch. This is an API-layer change |
| The BFF restructure (browser → Next.js route handlers → Django) | Phase 11. Keep today's cross-origin call shape |
| allauth headless `/_allauth/…` | Nobody. It is allauth's, not DRF's, and is unaffected |
| New endpoints of any kind | Phases 13–15 |
| `keel-prd.md`, `docs/plans/*`, `docs/adr/*` | The orchestrator |

**No migrations.**

---

## What already exists — do not rebuild

`keel/core/authz.py` is the heart of this repo. Its `__init_subclass__`
registries (`registered_global_viewsets`, `registered_scoped_viewsets`) and
the import-time `ImproperlyConfigured` checks are what make invariants 2 and
7 enforceable. **The registration mechanism survives. Only the base class
under it changes.** If you find yourself deleting a registry, you have taken
a wrong turn.

Likewise `keel/organizations/permissions.py` — the guards, the `Decision`
type, and `has_perm` are framework-independent and must not change. What
changes is how a request reaches them.

---

## 10.A — Core primitives

The spike, and the stage that decides whether this phase continues.

**Mount a Ninja `NinjaAPI` alongside DRF**, both routed, DRF still serving
every existing URL. Nothing moves yet.

**Authentication.** A Ninja auth callable over Django's session, preserving
the 401-vs-403 distinction `keel/core/authentication.py` exists to protect —
read its docstring, the reasoning is not obvious. Anonymous request to a
protected route answers **401**; authenticated-but-unpermitted answers
**403**. Deny by default: an operation that declares no auth must be
unreachable, matching today's `DEFAULT_PERMISSION_CLASSES`.

**Error envelope.** Ninja exception handlers producing
`{"error": {"code", "message", "details"}}` for every status in PRD §7's
table: 400, 401, 402, 403, 404, 409, 422, 429. Keep the `DomainError`
hierarchy's codes and messages identical; only the base class changes off
DRF's `APIException`. Pydantic `ValidationError` must map to the same
`validation_error` shape with the same `{field, message}` detail list that
`_validation_details` produces today.

**Cursor pagination.** The hard one. Read `keel/core/pagination.py`'s
docstring before writing a line: DRF's cursor encodes a within-tie offset
alongside the ordering value, so a page boundary inside a run of equal sort
values neither skips nor repeats rows. Ninja ships no cursor paginator.

Port the behaviour and **prove it**: a test with ≥60 rows sharing a single
`created_at`, paged end to end, asserting every row appears exactly once.
Write that test first, against the current DRF implementation, and watch it
pass — then make it pass on Ninja. A hand-rolled "cursor = last id seen"
will pass a naive test and fail this one.

**Org scoping and permissions.** `OrgScopedViewSet.initial()` becomes a
Ninja dependency or router-level callable that resolves the organisation
through `settings.KEEL_ORGANIZATION_RESOLVER`, raises `Http404` on `None`
(**404, never 403** — the resolver deliberately conflates "no such org" and
"not a member"), and runs `required_permissions` through `has_perm`,
raising `PermissionDeniedWithReason` carrying `Decision.reason` and
`Decision.details`.

**The registries.** Whatever replaces `GlobalViewSet` / `OrgScopedViewSet` —
most likely a router-factory plus a declaration object — must still refuse
at import time to exist without `required_permissions` and either
`organization_scoped = True` + `test_factory` or a `GLOBAL_JUSTIFICATION`,
and must still record itself in a walkable registry.

**Throttling.** DRF's `UserRateThrottle`/`AnonRateThrottle` go away with
DRF. Reimplement over Django's cache, preserving 429 + `Retry-After` and the
`KEEL_API_THROTTLE_USER_RATE` / `_ANON_RATE` settings.
`tests/test_rate_limiting.py` must pass unchanged.

**Stage gate.** 10.A is done when a scratch endpoint exercises all of the
above and the meta-tests still pass on the DRF side. Do not proceed until
the pagination tie test passes.

---

## 10.B — The invariant meta-tests, and one migrated app

Migrate **`keel/widgets/`** — the demo resource, one viewset, the thing
`/new-resource` generates. It is the smallest complete slice and the one
whose shape every future resource copies.

Then rewrite the meta-tests to walk both worlds:

- `tenant_isolation.py::iter_org_scoped_viewsets` walks a DRF router's
  `.registry` of `(prefix, viewset, basename)`. Ninja exposes
  `path_operations` on a `Router`, keyed by path, with no action concept.
  It needs an equivalent that finds the retrieve-shaped operation and
  drives it.
- `assert_cross_org_404` drives `retrieve` via `APIRequestFactory`. Ninja
  operations are plain functions; use Django's test client against the real
  URL instead, which is closer to the truth anyway.
- `test_meta_router_wiring.py` must fail if a scoped operation exists that
  the walk cannot reach — on **either** router, for as long as both exist.

**Prove each meta-test still bites.** For each of the three invariants,
deliberately break it, paste the failure into your report, restore it:
remove a `test_factory`; remove a `GLOBAL_JUSTIFICATION`; make a scoped
queryset ignore the organisation filter and confirm the cross-org test goes
red with 200-not-404.

This is the abort gate. If any of the three cannot be made to bite as hard
as it does today, stop here and report.

---

## 10.C — Migrate the remaining apps

In this order, smallest coupling first: `audit`, `billing`, `jobs`,
`files`, `organizations`. `organizations` last — it holds `MeView`,
`PermissionsRegistryView`, `InvitationAcceptView` and the transfer flow, and
it is where the permission integration is most intricate.

Per app: serializers → Ninja `Schema`s, viewsets → routers, `urls.py`
remounted. **URL shapes do not change**, apart from the `organizations` →
`orgs` rename and the `/plans/` envelope named above. `keel/billing/webhooks.py`'s Stripe
endpoint is CSRF-exempt and signature-verified — carry both properties over
and test them; a webhook that starts requiring CSRF fails only in
production.

Delete each DRF viewset as its Ninja replacement lands. Do not leave both.

---

## 10.D — OpenAPI and the generated client

`scripts/merge_openapi.py` builds the drf-spectacular document in-process
and merges it with allauth headless's. Replace the first input with Ninja's
`api.get_openapi_schema()`.

**Determinism is the whole point of that script** — read its docstring. The
merge must produce byte-identical output run to run, or the CI drift gate
fails randomly on unrelated changes and eventually gets disabled.

Ninja emits OpenAPI 3.1 by default; allauth headless emits 3.0.3 and
`SPECTACULAR_SETTINGS["OAS_VERSION"]` pins drf-spectacular to match, so the
two documents share a dialect. **Pin Ninja to 3.0.3 as well, or the merged
document mixes 3.0 and 3.1 JSON Schema variants and orval generates
nonsense.** Verify which orval actually supports before choosing.

Regenerate the client. Then walk the diff of `openapi.merged.json` route by
route and confirm the only changes are operation IDs and schema names.
Anything else is a regression from 10.C — go back and fix it there.

---

## 10.E — `apps/web`, and removing DRF

41 import sites in `apps/web` reference `@keel/api-client`. Operation IDs
and exported type names have changed; fix every call site. `pnpm --filter
web typecheck` is the gate, but it is not sufficient — run the Playwright
suites too, because a wrong-but-type-compatible symbol will compile.

Then remove DRF: `rest_framework` and `drf-spectacular` out of
`apps/api/pyproject.toml`, `REST_FRAMEWORK` and `SPECTACULAR_SETTINGS` out
of `config/settings/base.py`, `django-ninja` in. `grep -rn "rest_framework"
apps/api` must return nothing. Update the `contracts` and `test-api` CI jobs
if any step names DRF.

---

## Acceptance — evidence required

- [ ] `grep -rn "rest_framework" apps/api` returns nothing; DRF and drf-spectacular are out of `pyproject.toml`
- [ ] Every URL in `openapi.merged.json` is unchanged in path, method and status codes, apart from the three allowed changes — diff walked route by route and pasted in the report
- [ ] `/api/v1/orgs/…` serves everything `/api/v1/organizations/…` did; no reference to the old segment remains in `apps/api` or `apps/web`
- [ ] `GET /api/v1/plans/` returns the cursor envelope `{results, next, previous}`
- [ ] The error envelope is byte-identical for all of 400/401/402/403/404/409/422/429, each with a test
- [ ] Anonymous → **401**, authenticated-unpermitted → **403**, cross-tenant → **404**, each tested
- [ ] Cursor pagination passes the ≥60-tied-rows test with no skipped or repeated row
- [ ] All three invariant meta-tests bite: each broken deliberately, failure output pasted, restored
- [ ] `tests/test_rate_limiting.py` passes unchanged; 429 still carries `Retry-After`
- [ ] Stripe webhook is still CSRF-exempt and signature-verified, tested
- [ ] `merge_openapi.py` is deterministic — run twice, `git diff` empty
- [ ] Generated client regenerated; `api-client-generation` CI job green
- [ ] `pnpm --filter web typecheck` green and Playwright suites pass
- [ ] Per-directory coverage floors still met, including the 100% floors on `authz.py` and `pagination.py`
- [ ] `lint-imports` green — the import-linter contracts must not need loosening
- [ ] No migration generated

---

## How to work

One worktree, five stages, in order. Commit per stage; do not squash — the
stage boundaries are the record of how this was done, and the ADR's abort
condition depends on 10.A and 10.B being separable.

Do not start 10.C until 10.B's meta-tests bite.

## Report back

- The failure output from each deliberately-broken invariant in 10.B
- The route-by-route `openapi.merged.json` diff summary
- Anything DRF was doing that you had to reimplement rather than port, and
  whether the reimplementation is as good — specifically the paginator and
  the throttle
- Any place the invariants ended up **weaker**, however small. This is the
  one thing that must not be discovered later
- Whether the ADR's judgement held up in practice, honestly
