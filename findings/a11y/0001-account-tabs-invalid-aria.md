---
type: a11y
severity: major
status: open
slice: baseline
source: playwright
evidence: []
---

# Account pages: tabs fail `aria-valid-attr-value`

`/account/profile`, `/account/security` and `/account/sessions` have axe
`aria-valid-attr-value` violations on the Profile/Security/Sessions tab list
when rendered for a signed-in session. The page also sits on "Loading…".

**Why CI never caught it:** `e2e/accessibility.spec.ts` sets its fake
`sessionid` cookie on `http://localhost:3100` while CI browses
`http://lvh.me:3100`, so the cookie is never sent and the "account route"
tests axe-check the login redirect instead of the account pages.

**Repro:** in `accessibility.spec.ts`, set the cookie on the test's
`baseURL` instead of `localhost`, then run `pnpm e2e e2e/accessibility.spec.ts`.

**Fix direction:** make the tabs' `aria-controls` point at panels that are
always rendered (or drop `aria-controls` for unmounted panels), then fix the
spec's cookie host so it really tests authenticated account pages.
