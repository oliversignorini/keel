/** Display helpers shared by the pricing page, the billing settings page,
 * and the banners. */

/** Stripe stores amounts in minor units (PRD §4 "Billing flow"); the
 * pricing page shows major ones. */
export function formatPrice(unitAmount: number, currency: string): string {
  const amount = unitAmount / 100;
  try {
    return new Intl.NumberFormat(undefined, {
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
  return date.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}
