# ADR 0003 — `/api/v1` is an Experimental Preview, not a versioning promise

**Status:** Accepted — 2026-08-28
**Decides:** api-patterns finding 20 — `/api/v1/` signals a version but
publishes no life-cycle guarantee.
**Depends on:** ADR 0001 (Django Ninja), ADR 0002 (auth BFF shape).

---

## Context

`keel/core/ninja_api.py` sets `info.version: "1.0.0"` and every route lives
under a `v1` path prefix (`config/urls.py`) — a Version Identifier, and a
correct one. But nothing states what `v1` _commits to_. There is no
deprecation policy, no `Deprecation` / `Sunset` header, no stated
"Two in Production" support window, no SLA, and `docs/adr/` held only the
Ninja-over-DRF decision before this one.

_Patterns for API Design_ is explicit that this must be published
_before_ first release, and that "no commitment" — **Experimental
Preview** — is one of four legitimate, _recorded_ choices (the others
being Aggressive Obsolescence, Prolonged Blossoming, and Renaming). Silence
is not a fifth option: it just means every consumer independently guesses,
and guesses the strongest reading by default.

Keel is not a product with users — **it is a template**. Every project
instantiated from it inherits whatever `v1` means here, on day one, before
that project has decided anything about its own API's life cycle. Two
readings were on the table:

1. **Experimental Preview.** `v1` means "not yet stable" — breaking
   changes can ship without a version bump, consumers should expect churn,
   and the guarantee is explicitly _revisited_ once a real project
   forks this template and ships its first paying integration.
2. **Aggressive Obsolescence.** `v1` is load-bearing from the start —
   breaking changes require a `v2` prefix, `v1` gets a stated deprecation
   window, and `Deprecation`/`Sunset` headers are wired in from this
   commit.

## Decision

**Experimental Preview**, for the template as it ships today.

- `/api/v1/` is the correct prefix to keep — a Version Identifier should
  exist from the first release, and removing it later would be its own
  breaking change to every consumer. What Experimental Preview changes is
  the _promise_, not the _path_.
- No `Deprecation` / `Sunset` header machinery is added in this phase.
  Building a deprecation pipeline for an API with zero real consumers is
  solving a problem that doesn't exist yet, and would be one more piece of
  infrastructure every project forked from this template has to either
  keep working or rip out.
- `scripts/check_openapi_compat.py` (ADR 0002, ddia finding 25) still
  enforces additive-only changes to the _merged_ spec run-to-run — that
  check is about catching accidental breakage during this template's own
  development, not a life-cycle promise to external consumers. It is
  compatible with, and stays useful under, either reading in this ADR:
  tightening it into a real backward-compatibility gate is exactly the
  first thing a project should do the moment it flips to Aggressive
  Obsolescence.
- `keel.core.ninja_api.api`'s `description` now states the rate-limiting
  policy (api-patterns finding 7) and points at this ADR, so a reader of
  the OpenAPI document — not just this file — can find the life-cycle
  commitment.

### The "accepting that" clauses

Choosing Experimental Preview means accepting, explicitly, the
consequences the pattern names:

- **A consumer of a real project forked from this template gets no
  contractual warning before a breaking change**, until that project's
  own team makes a different, deliberate choice (most likely Aggressive
  Obsolescence, once the API has a first external caller worth
  protecting).
- **The generated TypeScript client
  (`packages/api-client/src/generated`) is the only compatibility net**
  most consumers will actually feel — a breaking schema change fails the
  client-regeneration CI job loudly, at build time, before it fails a
  real caller at runtime. This is a weaker guarantee than a published
  deprecation window, and is accepted as such.
- **`scripts/check_openapi_compat.py`'s additive-only check is a
  development-time guardrail, not this ADR's guarantee** — it can catch
  an accidental break; it cannot substitute for a real project's own
  decision about what `v1` means once it has users.

## Why not the other two

**Prolonged Blossoming** (support every version indefinitely) is wrong
for a template with a single, small, actively-changing API surface —
there is nothing yet worth the operational cost of running multiple
versions in parallel.

**Renaming** (a new name per breaking change, `v1`/`v2` as different
resource names rather than a version scheme) doesn't fit a Ninja/DRF-style
REST API where the version already lives in the path prefix by
convention; adopting it here would be a bigger structural change than
this phase's scope, for a benefit (per-resource versioning granularity)
nothing in this codebase needs yet.

## What this settles from the review findings

- **api-patterns finding 20**: recorded here — `v1` is Experimental
  Preview, not silence.
- **api-patterns finding 7** (rate limits invisible until hit): the
  `X-RateLimit-Limit` / `-Remaining` / `-Reset` headers `keel.core.
ninja_throttle` now emits, and the policy note in `ninja_api.api`'s
  `description`, are the "stated policy" half of that finding — filed
  here because both are, in the end, part of what a consumer needs
  published about this API's contract.

## Consequences

- **The first thing a real project forked from this template should do**,
  once it has an external API consumer worth protecting, is replace this
  ADR's decision with Aggressive Obsolescence (or whichever guarantee
  fits) and build the `Deprecation`/`Sunset` header machinery this phase
  deliberately did not.
- **No code changed to implement this ADR** beyond the `ninja_api.api`
  description note above — the decision itself, and its "accepting that"
  clauses, are the deliverable.
