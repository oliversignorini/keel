/**
 * `<ImpersonationBanner>` (PRD §5 component inventory: "Persistent,
 * unmissable, with an exit action"; PRD §6 "Impersonation";
 * docs/plans/phase-8.md 8.3). Renders only when `impersonatorEmail` is
 * given — the caller (apps/web's app layout) decides that from
 * `/api/v1/me/`'s `impersonator` field, which is non-null only for an
 * impersonated session.
 *
 * Deliberately has no close/dismiss control of any kind — "cannot be
 * dismissed" is the acceptance criterion, not merely the default state.
 */
export function ImpersonationBanner({
  impersonatorEmail,
  targetEmail,
  onExit,
}: {
  impersonatorEmail: string;
  targetEmail: string;
  onExit: () => void;
}) {
  return (
    <div
      role="status"
      className="sticky top-0 z-40 flex items-center justify-center gap-3 bg-amber-500 px-4 py-2 text-sm font-medium text-amber-950 dark:bg-amber-600 dark:text-amber-50"
    >
      <span>
        {impersonatorEmail} is impersonating {targetEmail}
      </span>
      <button
        type="button"
        onClick={onExit}
        className="rounded-md border border-amber-950/30 px-2 py-0.5 font-semibold hover:bg-amber-950/10 dark:border-amber-50/30 dark:hover:bg-amber-50/10"
      >
        Exit impersonation
      </button>
    </div>
  );
}
