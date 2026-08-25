# Phase 7 — Marketing site and blog

**Source of truth:** `keel-prd.md` v1.2 — §5 Routes (the `(marketing)` group), §3 answer F (SEO coupling), §8 Phase 7, and §8 Phase 9's note that `init` can delete this whole group.
**Depends on:** Phase 4, merged. **Independent of Phases 5, 5.5, 6** — this is why it runs now rather than last.
**Size:** Small.

---

## Boundary

**In scope:** the `(marketing)` route group, landing page, pricing page, MDX blog via `content-collections`, legal pages, `sitemap.xml`, `robots.txt`, Open Graph images, JSON-LD.

**Out of scope:**

| Thing | Owner |
|---|---|
| Anything under `apps/api` | Phase 5 is working there right now — **do not touch it** |
| `<AppShell>`, command palette, `<DataTable>` | Phase 6 |
| Sentry, PostHog, `axe-core` in CI | Phase 8 |
| The `init` script that deletes this group | Phase 9 |
| `keel-prd.md`, anything under `docs/plans/` | The orchestrator |

**The pricing page already exists**, built by `p4-billing-web`, reading live from `GET /api/v1/plans/`. Move it into the `(marketing)` group rather than rewriting it, and keep it working.

---

## Tasks

### 7.1 — The route group

`(marketing)` per §5: `/`, `/pricing`, `/blog`, `/blog/[slug]`, `/legal/terms`, `/legal/privacy`.

**Statically rendered.** The Lighthouse SEO gate (≥ 95) is an acceptance criterion, and it is unreachable if these pages render per-request.

Use the `[data-surface="marketing"]` hook the token contract already provides (§5, "Tokens are declared on a nestable selector") if the marketing surface wants different tokens from the app. Most projects won't; don't invent a second theme for the sake of it.

### 7.2 — Landing page

Restrained. This is a **template**, and §5 is explicit: a boilerplate with a strong identity is one every project has to fight. Structure and semantics over decoration — a project's brand pass replaces `packages/ui/theme.css` and nothing else should need to change.

### 7.3 — Pricing

Already built. Move it in, keep it reading live from the API, keep the monthly/annual toggle.

**Two known defects to fix while you are here:**

1. Feature lists render raw entitlement codes — `api_access`, `audit_log`, `custom_roles`. Map them to human labels. Keep the mapping in one place, since Phase 9's `/new-resource` will add entitlements and needs somewhere obvious to register a label.
2. `formatPrice` and `formatDate` in `apps/web/lib/billing/format.ts` pin the locale to `en-AU` deliberately — a hydration mismatch on this exact page is what forced that. **Do not un-pin it**, and read the comment before touching either function.

### 7.4 — Blog

MDX via `content-collections`, typed frontmatter. Posts are files in the repo, not a CMS — a CMS is a per-project decision.

Ship two or three real posts so the index, the slug route and the typed frontmatter are all genuinely exercised. A blog with no posts proves nothing.

### 7.5 — SEO plumbing

`sitemap.xml` including marketing and blog routes and **excluding `/app/*`**. `robots.txt`. Open Graph image route. JSON-LD.

### 7.6 — Make Phase 9's deletion possible

PRD Phase 9: `init` on "no" deletes the route group, `content-collections`, the MDX content directory, the sitemap and robots routes, and the marketing rows in the Playwright suite.

Build so that is a clean excision: keep marketing-only dependencies out of shared packages, keep marketing-only Playwright specs in their own file, and leave a short note in `docs/` listing exactly what `init` must remove. You are the person who knows; Phase 9 will not.

---

## Acceptance — evidence required

- [ ] Marketing routes are statically rendered and score ≥ 95 on Lighthouse SEO
- [ ] Pricing reflects Stripe without a redeploy, and still shows live plans
- [ ] Feature lists show human labels, not raw entitlement codes
- [ ] A new MDX file appears in the index with typed frontmatter validation — demonstrated by adding one with a bad frontmatter field and showing the build fail
- [ ] Sitemap includes marketing and blog routes and excludes `/app/*`
- [ ] Zero hydration errors in the browser console on every marketing route — check this by loading each page, not by reasoning about it
- [ ] `docs/` lists exactly what `init` must remove to delete the marketing site
- [ ] Nothing under `apps/api` was modified

---

## How to work

- Tests alongside the code, using the `mattpocock-skills:tdd` skill.
- **Load the pages in a browser and read the console.** The one real bug found in Phase 4's frontend was a hydration mismatch that every test passed straight through. Playwright is available.
- Run `eslint`, `prettier`, `tsc` and `vitest` before claiming done.
- Update the Orca worktree comment at each task boundary.
- Do not push, do not open a PR — the orchestrator merges.
- Every commit message body ends with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AQXQvAv8g92xotjrnnibLc
```

## Report back

Acceptance boxes with evidence; the Lighthouse score; the `init` removal list; anything in the PRD that looked wrong from inside the code.
