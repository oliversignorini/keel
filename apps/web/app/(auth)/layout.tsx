import Link from "next/link";

// (auth) route group: no app chrome, a centred card. AppShell is the app
// shell's own concern — these pages exist before a signed-in user has
// anywhere to be shown a shell around. The wordmark is the only way back
// out to the marketing site from here.
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-12">
      <Link
        href="/"
        className="mb-6 rounded-md text-lg font-semibold text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        Keel
      </Link>
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-sm">
        {children}
      </div>
    </div>
  );
}
