import { LogOut, UserCog } from "lucide-react";

import { Button } from "./components/ui/button";

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
 * Uses the `warning` token (not `alert variant="warning"`, which would
 * dismiss like any other alert) styled as a persistent bar.
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
      className="sticky top-0 z-40 flex items-center justify-center gap-3 bg-warning px-4 py-2 text-sm font-medium text-warning-foreground"
    >
      <UserCog className="size-4 shrink-0" />
      <span>
        {impersonatorEmail} is impersonating {targetEmail}
      </span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onExit}
        className="border-warning-foreground/30 bg-transparent text-warning-foreground hover:bg-warning-foreground/10"
      >
        <LogOut />
        Exit impersonation
      </Button>
    </div>
  );
}
