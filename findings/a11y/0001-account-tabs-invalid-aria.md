---
type: a11y
severity: major
status: fixed
slice: S1
source: playwright
evidence:
  - findings/_evidence/S1/red.txt
  - findings/_evidence/S1/green.txt
  - findings/_evidence/S1/red-fix1.txt
  - findings/_evidence/S1/green-fix1.txt
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

**Round 1 (review follow-up):** the new `TabsContent` panel was a keyboard tab
stop with no visible focus indicator (WCAG 2.4.7). Since every account page's
content already contains focusable elements, added a `focusable` variant to
`TabsContent` in `packages/ui/src/components/ui/tabs.tsx` and set
`focusable={false}` on the account layout's panel so it's skipped in the tab
order entirely, per the WAI-ARIA tabs pattern. Also: the spec now asserts the
signed-in URL and a visible tablist before running axe; tab-to-content spacing
is restored via a new `spacing="relaxed"` variant on `Tabs` instead of a
call-site `className`; and `activeTab` now matches on exact/segment boundaries
and no longer falls back to "Profile" for an unrecognised `/account/*` route.
