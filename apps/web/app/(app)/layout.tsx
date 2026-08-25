"use client";

import { OrgSwitcher } from "@/components/org/org-switcher";
import { toApexHost } from "@/lib/host";
import { OrgProvider, useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { authLogout } from "@keel/api-client";
import { AppShell, CommandPalette, type CommandItem, ThemeToggleButton } from "@keel/ui";
import { useTheme } from "next-themes";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

/**
 * `<AppShell>` (PRD §5 Layout; docs/plans/phase-6.md 6.B) — top bar with
 * the org switcher, primary nav, command palette, dark-mode toggle and
 * account menu, wrapping every `/app/[org]/*` (visible: `/[org]/*` on
 * the app host — plan 6.A) page.
 *
 * `<OrgProvider>` wraps the whole group (not just `/[org]/*`) so
 * `<OrgSwitcher>` has the caller's organisation list even on the bare
 * app-root redirect page, which has no `[org]` segment yet.
 *
 * Phase 5.5 (`<JobTray>`, `useJobStream`, SSE) has not landed as of this
 * phase — the slot below is reserved and renders nothing rather than a
 * placeholder, so there's no visible gap to redesign around once it
 * does.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ org?: string }>();

  return (
    <OrgProvider orgSlug={params.org ?? ""}>
      <AppLayoutShell>{children}</AppLayoutShell>
    </OrgProvider>
  );
}

function AppLayoutShell({ children }: { children: React.ReactNode }) {
  const params = useParams<{ org?: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { me, currentOrg } = useOrgContext();
  const { resolvedTheme, setTheme } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function signOut() {
    await authLogout();
    // /login only exists on the apex (plan 6.A).
    window.location.href = `${window.location.protocol}//${toApexHost(window.location.host)}/login`;
  }

  const navItems = useMemo(() => {
    if (!params.org) return [];
    const items: { href: string; label: string; requires?: string }[] = [
      { href: `/${params.org}`, label: "Dashboard" },
      { href: `/${params.org}/widgets`, label: "Widgets", requires: Perm.WIDGETS_VIEW },
      { href: `/${params.org}/settings/general`, label: "Settings" },
    ];
    // Nav visibility is presentation only, the same as <Can> (components
    // /org/can.tsx) — the widgets route itself still enforces
    // Perm.WIDGETS_VIEW server-side regardless of whether a link to it
    // is rendered here.
    return items.filter(
      (item) => !item.requires || currentOrg?.permissions.includes(item.requires),
    );
  }, [params.org, currentOrg]);

  const paletteItems = useMemo<CommandItem[]>(() => {
    const navCommands: CommandItem[] = navItems.map((item) => ({
      id: `nav-${item.href}`,
      label: item.label,
      group: "Navigate",
      onSelect: () => router.push(item.href),
    }));
    const orgCommands: CommandItem[] = (me?.organizations ?? []).map((org) => ({
      id: `org-${org.slug}`,
      label: `Switch to ${org.name}`,
      group: "Organisations",
      onSelect: () => router.push(`/${org.slug}`),
    }));
    const all = [...navCommands, ...orgCommands];
    if (!paletteQuery) return all;
    const query = paletteQuery.toLowerCase();
    return all.filter((item) => item.label.toLowerCase().includes(query));
  }, [navItems, me, paletteQuery, router]);

  const nav = (
    <>
      {navItems.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={pathname === item.href ? "page" : undefined}
          className="text-foreground hover:text-foreground/80 aria-[current=page]:font-medium"
        >
          {item.label}
        </Link>
      ))}
    </>
  );

  return (
    <>
      <AppShell
        logo={
          <Link href="/" className="text-sm font-semibold text-foreground">
            Keel
          </Link>
        }
        orgSwitcher={<OrgSwitcher />}
        nav={nav}
        commandPaletteTrigger={
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="rounded-md border border-input px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
          >
            <span aria-hidden="true">⌘K</span>
            <span className="sr-only">Open command palette</span>
          </button>
        }
        themeToggle={
          <ThemeToggleButton
            isDark={resolvedTheme === "dark"}
            onToggle={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          />
        }
        accountMenu={
          <div className="flex items-center gap-3 text-sm">
            <Link href="/account/profile" className="text-muted-foreground hover:text-foreground">
              Account
            </Link>
            <button
              type="button"
              onClick={() => void signOut()}
              className="text-muted-foreground underline hover:text-foreground"
            >
              Sign out
            </button>
          </div>
        }
        // Phase 5.5 owns <JobTray> / useJobStream / SSE — not built yet
        // (docs/plans/phase-6.md 6.C). This is the reserved slot; it
        // renders nothing until that worktree lands and this becomes
        // `<JobTray orgSlug={currentOrg?.slug} />`.
        jobTraySlot={null}
      >
        {children}
      </AppShell>
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        items={paletteItems}
        query={paletteQuery}
        onQueryChange={setPaletteQuery}
      />
    </>
  );
}
