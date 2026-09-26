---
type: code
severity: major
status: open
slice: baseline
source: playwright
evidence: []
---

# Three e2e specs never run in CI and fail locally

CI's `e2e` job runs only `accessibility.spec.ts` and `auth-flows.spec.ts`
(`pnpm e2e:baseline` mirrors that and passes). The rest of `apps/web/e2e`
fails against a fresh slot:

| Spec                                  | Failure                                                                | Likely cause                                                                                                                                                                                                    |
| ------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `cross-host-login.spec.ts` (2 tests)  | **Resolved (S3).** Was "stays on `/login?next=`"                       | now logs in as the seeded `owner@demo.keel.test` in `demo-org` (`seed_demo`) instead of an unseeded `e2e@example.com`/`E2E Org`; CI runs `seed_demo` before it; added to `e2e:baseline` and CI's `e2e` job    |
| `org-permissions.spec.ts`             | **Resolved (S2).** Was "config endpoint should set a csrftoken cookie" | now calls the API on `api.lvh.me` (`E2E_API_LVH_URL`, default `http://api.lvh.me:8000`), matching the `.lvh.me` cookie domain; added to `e2e:baseline` and CI's `e2e` job                                     |
| `app-accessibility.spec.ts` (2 tests) | CSP cross-origin fetch "Failed to fetch"; route axe run aborts         | needs the lvh.me topology plus CORS for the app origin; written for `playwright.cross-host.config.ts`, but the default config also picks it up                                                                |

**Fix direction:** either add these to CI with the setup they need (seed
command, `api.lvh.me` URLs, cross-host config), or exclude them from the
default config via `testIgnore` so `pnpm e2e` is green by default. Until
then, factory gates use `pnpm e2e:baseline` plus slice-tagged specs.
