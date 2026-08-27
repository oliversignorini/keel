# Phase 18 — Portfolio polish and v1.0

**Source of truth:** Notion "Keel Phase 16 — Portfolio polish and reusable docs", plus the "Open-source release polish" checklist.
**Depends on:** Phase 17 merged.
**Size:** Small.

---

## What this is

The last pass. Phase 9 made the repository *not embarrassing*; this makes it
*persuasive*. Almost all the writing is done by now — `docs/architecture.md`,
`docs/auth-flow.md`, `docs/storage.md`, `docs/billing.md`,
`docs/jobs-and-audit.md`, `docs/query-patterns.md`, `docs/maintenance.md`,
`docs/deploy-railway.md`. This phase makes the front door match them.

## Boundary

**In scope:** `README.md`, screenshots, `CHANGELOG.md`, release tagging, and
corrections to existing docs.

**Out of scope:** application code, `init`, new features. If something needs
fixing in `apps/`, it goes on the roadmap, not in this diff.

## Work

**Rewrite `README.md`** around who Keel is for. It should answer, in this
order and above the fold: what it is, who it is for, what you get, **what it
is not**, and how to run it in five minutes.

"What Keel is not" earns its place — a practical SaaS boilerplate, not an AI
starter kit, not a framework, not a hosted product. Being clear about the
boundary is what makes the rest credible.

Lead the technical section with the invariants, because they are the actual
differentiator. Most boilerplates are a pile of features; this one is a pile
of features plus a build that fails when you break the tenant boundary. Show
that.

**Screenshots**, or a short GIF of the signup → organisation → demo resource
flow. Real screenshots of the running app, not mockups.

**Architecture diagram** in the README itself, not only in `docs/`.

**Roadmap section** — what is deliberately absent and what is planned. Brein
gets a sentence: the first product built on Keel, not part of it.

**Changelog and tag.** `CHANGELOG.md` up to date, then tag `v1.0.0`. A
repository with no releases reads as abandoned; one release reads as
finished.

**Final fresh-clone check.** Clone into a clean directory, follow the README
exactly, and record every step where you had to know something the README
did not tell you.

## Acceptance — evidence required

- [ ] README answers what / who / what you get / what it is not / how to run, above the fold
- [ ] The invariants are prominent, with the enforcing files named
- [ ] Screenshots or a GIF of the real running application
- [ ] Architecture diagram renders in the README on GitHub
- [ ] Roadmap present; Brein's relationship stated in one sentence
- [ ] `CHANGELOG.md` current; `v1.0.0` tagged
- [ ] Fresh-clone run completed by following the README only, with every gap fixed
- [ ] Every internal documentation link resolves — checked, not assumed

## Report back

What a stranger would still not understand after ten minutes with this
repository.
