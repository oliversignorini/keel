"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { MenuIcon } from "lucide-react";

import { Button } from "./components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./components/ui/sheet";

/** `<AppShell>` — top bar, no sidebar, sticky, 56px:
 *
 *   [Logo] [Org ▾] │ Dashboard  Widgets  Settings │ [⌘K] [◐] [avatar]
 *
 * `orgSwitcher` sits immediately after the logo — tenant context must
 * always be visible, since an invisible active organization is the most
 * common source of "wrong data" confusion in multi-tenant apps. On
 * mobile, `nav` collapses into a `<Sheet>`; the org switcher stays in
 * the bar regardless of viewport.
 *
 * `jobTraySlot` is a named slot for a `<JobTray>` (`useJobStream`, SSE).
 * The shell only reserves where the tray mounts; it renders nothing when
 * no tray is supplied.
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

        <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
          <SheetTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Toggle navigation menu"
              className="ml-1 md:hidden"
            >
              <MenuIcon />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72">
            <SheetHeader>
              <SheetTitle>Navigation</SheetTitle>
              <SheetDescription className="sr-only">Site navigation</SheetDescription>
            </SheetHeader>
            <nav
              className="flex flex-col gap-1 px-2 text-sm text-muted-foreground [&_a]:rounded-md [&_a]:px-2 [&_a]:py-3"
              onClick={() => setMobileNavOpen(false)}
            >
              {nav}
            </nav>
          </SheetContent>
        </Sheet>

        <div className="ml-auto flex items-center gap-2">
          {commandPaletteTrigger}
          {themeToggle}
          {accountMenu}
        </div>
      </header>

      {jobTraySlot}

      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
