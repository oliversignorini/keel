"use client";

import { impersonationExitCreate } from "@keel/api-client";
import { ImpersonationBanner as BaseImpersonationBanner } from "@keel/ui";

import { useMe } from "@/lib/org/use-me";

/**
 * Wires `<ImpersonationBanner>` (packages/ui, presentation only) to
 * `/api/v1/me/`'s `impersonator` field and the exit endpoint (PRD §6
 * "Impersonation"; docs/plans/phase-8.md 8.3). Used in every layout an
 * impersonated session can reach — `(app)` and `account` — rather than
 * built into a single shared shell, since those two route groups don't
 * share one (`account/layout.tsx` deliberately renders outside
 * `<AppShell>`).
 */
export function ImpersonationBannerHost() {
  const { me } = useMe();

  if (!me?.impersonator) return null;

  async function exit() {
    await impersonationExitCreate();
    window.location.reload();
  }

  return (
    <BaseImpersonationBanner
      impersonatorEmail={me.impersonator.email}
      targetEmail={me.user.email}
      onExit={() => void exit()}
    />
  );
}
