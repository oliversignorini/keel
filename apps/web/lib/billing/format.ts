/** Display helpers shared by the pricing page, the billing settings page,
 * and the banners. */

/** The locale every server-rendered price and date is formatted in.
 *
 * This is pinned rather than left as `undefined` on purpose. `undefined`
 * means "the runtime's locale", and the runtime differs either side of
 * hydration: Node formats AUD as "$29", a browser set to en-AU formats
 * the same value as "A$29". React then reports a hydration mismatch and
 * throws away the server-rendered tree — on the pricing page, which PRD
 * §8 Phase 7 requires to be statically rendered and indexed.
 *
 * A project changing its default currency changes this line too. When
 * per-user locales are needed, resolve one on the server and pass it
 * down, so both renders agree on the same value.
 */
const LOCALE = "en-AU";

/** Stripe stores amounts in minor units (PRD §4 "Billing flow"); the
 * pricing page shows major ones. */
export function formatPrice(unitAmount: number, currency: string): string {
  const amount = unitAmount / 100;
  try {
    return new Intl.NumberFormat(LOCALE, {
      style: "currency",
      currency: currency.toUpperCase(),
      // Whole-dollar prices are the common case and "$19" reads better
      // than "$19.00"; a price with cents still shows them.
      minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    }).format(amount);
  } catch {
    // An unknown currency code from Stripe should degrade, not throw.
    return `${amount.toFixed(2)} ${currency.toUpperCase()}`;
  }
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(LOCALE, { day: "numeric", month: "long", year: "numeric" });
}
