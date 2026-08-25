import Link from "next/link";

/** The `(marketing)` route group (PRD §5): `/`, `/pricing`, `/blog`,
 * `/blog/[slug]`, `/legal/terms`, `/legal/privacy` — the only routes
 * `init` needs to delete to remove the marketing site (PRD §8 Phase 9;
 * see docs/marketing-removal.md).
 *
 * `data-surface="marketing"` is the token-contract hook (packages/ui/theme.css)
 * for a per-project brand pass that wants different tokens here than in
 * the app shell — empty by default, per phase-7.md's "most projects
 * won't; don't invent a second theme for the sake of it". */
export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div data-surface="marketing" className="flex min-h-screen flex-col">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <nav className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <Link href="/" className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            Keel
          </Link>
          <div className="flex items-center gap-6 text-sm">
            <Link href="/pricing" className="text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100">
              Pricing
            </Link>
            <Link href="/blog" className="text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100">
              Blog
            </Link>
            <Link
              href="/login"
              className="text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
            >
              Log in
            </Link>
            <Link
              href="/signup"
              className="rounded-md bg-neutral-900 px-3 py-1.5 font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
            >
              Sign up
            </Link>
          </div>
        </nav>
      </header>
      <div className="flex-1">{children}</div>
      <footer className="border-t border-neutral-200 dark:border-neutral-800">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-8 text-sm text-neutral-600 dark:text-neutral-400 sm:flex-row sm:justify-between">
          <p>&copy; {new Date().getFullYear()} Keel</p>
          <div className="flex gap-4">
            <Link href="/legal/terms" className="hover:text-neutral-900 dark:hover:text-neutral-100">
              Terms
            </Link>
            <Link href="/legal/privacy" className="hover:text-neutral-900 dark:hover:text-neutral-100">
              Privacy
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
