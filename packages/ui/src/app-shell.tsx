"use client";

import type { ReactNode } from "react";
import { useState } from "react";

/** `<AppShell>` — top bar, no sidebar, sticky, 56px (PRD §5 Layout):
 *
 *   [Logo] [Org ▾] │ Dashboard  Widgets  Settings │ [⌘K] [◐] [avatar]
 *
 * `orgSwitcher` sits immediately after the logo — tenant context must
 * always be visible (PRD §5: "the single most common source of 'wrong
 * data' confusion in multi-tenant apps"). On mobile, `nav` collapses
 * into a sheet; the org switcher stays in the bar regardless of
 * viewport.
 *
 * `jobTraySlot` is a named slot for Phase 5.5's `<JobTray>`
 * (`useJobStream`, SSE) — that worktree owns the tray itself; this
 * phase only reserves where it mounts. Renders nothing when Phase 5.5
 * hasn't landed yet.
 */
export function AppShell({
  logo,
  orgSwitcher,
  nav,
  commandPaletteTrigger,
  themeToggle,
  accountMenu,
  jobTraySlot,
  children,
}: {
  logo: ReactNode;
  orgSwitcher: ReactNode;
  nav: ReactNode;
  commandPaletteTrigger?: ReactNode;
  themeToggle?: ReactNode;
  accountMenu?: ReactNode;
  jobTraySlot?: ReactNode;
  children: ReactNode;
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background px-4">
        {logo}
        {orgSwitcher}
        <nav className="hidden items-center gap-4 text-sm text-muted-foreground md:flex">{nav}</nav>
        <button
          type="button"
          aria-label="Toggle navigation menu"
          aria-expanded={mobileNavOpen}
          onClick={() => setMobileNavOpen((value) => !value)}
          className="ml-1 rounded-md p-1.5 text-foreground hover:bg-accent md:hidden"
        >
          <span aria-hidden="true">☰</span>
        </button>
        <div className="ml-auto flex items-center gap-2">
          {commandPaletteTrigger}
          {themeToggle}
          {accountMenu}
        </div>
      </header>

      {mobileNavOpen ? (
        <nav className="flex flex-col gap-1 border-b border-border bg-background px-4 py-3 text-sm text-muted-foreground md:hidden">
          {nav}
        </nav>
      ) : null}

      {jobTraySlot}

      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
