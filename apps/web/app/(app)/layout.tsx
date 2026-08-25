"use client";

import { authLogout } from "@keel/api-client";
import { OrgSwitcher } from "@/components/org/org-switcher";
import { OrgProvider } from "@/lib/org/org-context";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

/**
 * (app) route group layout (PRD §5 "Routes"). This is the "minimum honest
 * layout" phase-3.md Worktree C asks for, not `<AppShell>` — Phase 6 owns
 * the real top bar with the command palette, dark mode toggle, and
 * content container (PRD §5 "Layout — top bar navigation"). What's here
 * is only what this phase needs to be true: tenant context (the
 * organisation switcher) visible immediately after the logo on every
 * authenticated page, per PRD §5's placement requirement, and nothing
 * else. Phase 6 replaces this file's contents wholesale; nothing in it is
 * meant to survive that phase unchanged.
 *
 * `<OrgProvider>` wraps the whole group (not just `/app/[org]/*`) so
 * `<OrgSwitcher>` has the caller's organisation list even on the bare
 * `/app` redirect page, which has no `[org]` segment yet.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ org?: string }>();
  const router = useRouter();

  async function signOut() {
    await authLogout();
    router.push("/login");
  }

  return (
    <OrgProvider orgSlug={params.org ?? ""}>
      <div className="min-h-screen bg-neutral-50 dark:bg-neutral-950">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-neutral-200 bg-white px-4 dark:border-neutral-800 dark:bg-neutral-900">
          <Link
            href="/app"
            className="text-sm font-semibold text-neutral-900 dark:text-neutral-100"
          >
            Keel
          </Link>
          <OrgSwitcher />
          <nav className="flex items-center gap-4 text-sm text-neutral-600 dark:text-neutral-400">
            {params.org ? (
              <>
                <Link href={`/app/${params.org}`}>Dashboard</Link>
                <Link href={`/app/${params.org}/settings/general`}>Settings</Link>
              </>
            ) : null}
          </nav>
          <div className="ml-auto flex items-center gap-4 text-sm">
            <Link href="/account/profile" className="text-neutral-600 dark:text-neutral-400">
              Account
            </Link>
            <button
              type="button"
              onClick={() => void signOut()}
              className="text-neutral-600 underline dark:text-neutral-400"
            >
              Sign out
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
      </div>
    </OrgProvider>
  );
}
