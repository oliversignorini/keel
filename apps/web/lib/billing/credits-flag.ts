/**
 * The client-side mirror of Django's `BILLING_CREDITS`, off by default.
 *
 * `<CreditMeter>` renders only when credits are enabled, and with the
 * flag off there are no endpoints, no meter, and no cost — which means
 * *no request either* — a meter that has to call the API to
 * discover the feature is off has already paid the cost the flag exists
 * to avoid, once per page, for every organisation on a deployment that
 * will never turn credits on.
 *
 * Nothing here is enforcement. `CreditBalanceView` 404s when the server's
 * flag is off, whatever this value says, and `<CreditMeter>` renders
 * nothing on that 404 as well — so the two possible drift states are
 * "flag on here, off there" (one wasted request, no meter) and "off here,
 * on there" (no meter, no request). Neither shows a wrong balance, which
 * is the only failure that would matter.
 *
 * Read through a function rather than a module constant so a test can set
 * the variable per-case; Next.js inlines `process.env.NEXT_PUBLIC_*` at
 * build time in the browser bundle either way.
 */
export function creditsEnabled(): boolean {
  return process.env.NEXT_PUBLIC_BILLING_CREDITS === "true";
}
