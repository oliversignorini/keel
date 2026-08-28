import Link from "next/link";
import { buttonVariants } from "@keel/ui";

import { MarketingMobileNav } from "./_components/mobile-nav";

/** The `(marketing)` route group: `/`, `/pricing`, `/blog`,
 * `/blog/[slug]`, `/legal/terms`, `/legal/privacy` — the only routes
 * `init` needs to delete to remove the marketing site (see
 * docs/marketing-removal.md).
 *
 * `data-surface="marketing"` is the token-contract hook (packages/ui/theme.css)
 * for a per-project brand pass that wants different tokens here than in
 * the app shell. Every colour below resolves through that contract —
 * marketing states no palette of its own, so overriding the seam is a
 * change to four custom properties rather than forty class attributes.
 *
 * Only low-level primitives cross this boundary: no `<AppShell>`, no
 * `<DataTable>`, no `<CommandPalette>`, no `<OrgSwitcher>`, so deleting
 * the group leaves no dangling import. */
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-surface="marketing"
      className="flex min-h-screen flex-col bg-background text-foreground"
    >
      <header className="border-b border-border">
        <nav className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <Link href="/" className="text-lg font-semibold text-foreground">
            Keel
          </Link>
          <div className="hidden items-center gap-6 text-sm md:flex">
            <Link href="/pricing" className="text-muted-foreground hover:text-foreground">
              Pricing
            </Link>
            <Link href="/blog" className="text-muted-foreground hover:text-foreground">
              Blog
            </Link>
            <Link href="/login" className="text-muted-foreground hover:text-foreground">
              Log in
            </Link>
            <Link href="/signup" className={buttonVariants({ size: "sm" })}>
              Sign up
            </Link>
          </div>
          <MarketingMobileNav />
        </nav>
      </header>
      <div className="flex-1">{children}</div>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:justify-between">
          <p>&copy; {new Date().getFullYear()} Keel</p>
          <div className="flex gap-4">
            <Link href="/legal/terms" className="hover:text-foreground">
              Terms
            </Link>
            <Link href="/legal/privacy" className="hover:text-foreground">
              Privacy
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
