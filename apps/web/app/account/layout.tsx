import Link from "next/link";

import { ImpersonationBannerHost } from "@/components/org/impersonation-banner";

// Renders outside AppShell (Phase 6) on purpose — this is the honest
// minimum, not a shell Phase 6 will need to tear out. The impersonation
// banner (PRD §6; docs/plans/phase-8.md 8.3) still has to render here
// regardless — this is exactly where the password/MFA restrictions bite.
export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-12">
      <ImpersonationBannerHost />
      <nav className="flex gap-4 border-b border-neutral-200 pb-4 text-sm dark:border-neutral-800">
        <Link href="/account/profile" className="underline">
          Profile
        </Link>
        <Link href="/account/security" className="underline">
          Security
        </Link>
        <Link href="/account/sessions" className="underline">
          Sessions
        </Link>
      </nav>
      {children}
    </div>
  );
}
