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

| Spec                                  | Failure                                                        | Likely cause                                                                                                                                      |
| ------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cross-host-login.spec.ts` (2 tests)  | stays on `/login?next=`                                        | needs a pre-seeded `e2e@example.com` user and `E2E Org`; nothing seeds them                                                                       |
| `org-permissions.spec.ts`             | "config endpoint should set a csrftoken cookie"                | calls the API on `localhost`, but CSRF/session cookies are `Domain=.lvh.me`, so the request context never stores them. It should use `api.lvh.me` |
| `app-accessibility.spec.ts` (2 tests) | CSP cross-origin fetch "Failed to fetch"; route axe run aborts | needs the lvh.me topology plus CORS for the app origin; written for `playwright.cross-host.config.ts`, but the default config also picks it up    |

**Fix direction:** either add these to CI with the setup they need (seed
command, `api.lvh.me` URLs, cross-host config), or exclude them from the
default config via `testIgnore` so `pnpm e2e` is green by default. Until
then, factory gates use `pnpm e2e:baseline` plus slice-tagged specs.
