---
type: a11y
severity: major
status: fixed
slice: S1
source: playwright
evidence:
  - findings/_evidence/S1/red.txt
  - findings/_evidence/S1/green.txt
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

**Resolution:** wrapped `{children}` in a `TabsContent` inside `AccountLayout`'s
`Tabs` root (`apps/web/app/account/layout.tsx`) so Radix's `aria-controls` on
each `TabsTrigger` references a panel that is actually rendered; the spec now
sets the `sessionid` cookie on the test's `baseURL` fixture instead of a
hardcoded `localhost` host.
