import Link from "next/link";

// Renders outside AppShell (Phase 6) on purpose — this is the honest
// minimum, not a shell Phase 6 will need to tear out.
export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-12">
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
