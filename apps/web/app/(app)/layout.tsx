"use client";

import { JobTray } from "@/components/jobs/job-tray";
import { ImpersonationBannerHost } from "@/components/org/impersonation-banner";
import { OrgSwitcher } from "@/components/org/org-switcher";
import { toApexHost } from "@/lib/host";
import { OrgProvider, useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { listWidgets } from "@/lib/widgets/api";
import { authLogout } from "@keel/api-client";
import {
  AppShell,
  Avatar,
  AvatarFallback,
  Button,
  CommandPalette,
  type CommandItem,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Kbd,
  ThemeToggleButton,
} from "@keel/ui";
import { LogOut, Search, Settings, Shield, User } from "lucide-react";
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
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ org?: string }>();

  return (
    <OrgProvider orgSlug={params.org ?? ""}>
      <AppLayoutShell>{children}</AppLayoutShell>
    </OrgProvider>
  );
}

function accountInitials(nameOrEmail: string | undefined): string {
  if (!nameOrEmail) return "?";
  const letter = nameOrEmail.trim().charAt(0);
  return letter ? letter.toUpperCase() : "?";
}

function AppLayoutShell({ children }: { children: React.ReactNode }) {
  const params = useParams<{ org?: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { me, currentOrg } = useOrgContext();
  const { resolvedTheme, setTheme } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [widgetResults, setWidgetResults] = useState<{ id: string; name: string }[]>([]);
  const [isMac, setIsMac] = useState(true);

  useEffect(() => {
    setIsMac(/mac/i.test(window.navigator.userAgent));
  }, []);

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

  // Resource search: filters by name against the current page of
  // widgets. A real project's palette would back this with a proper
  // search endpoint; this demo resource has no such index, so it's a
  // client-side substring match over what's already paginated in.
  useEffect(() => {
    if (!paletteOpen || !currentOrg?.permissions.includes(Perm.WIDGETS_VIEW) || !paletteQuery) {
      setWidgetResults([]);
      return;
    }
    let cancelled = false;
    listWidgets(currentOrg.slug)
      .then((page) => {
        if (cancelled) return;
        const query = paletteQuery.toLowerCase();
        setWidgetResults(page.results.filter((w) => w.name.toLowerCase().includes(query)));
      })
      .catch(() => {
        if (!cancelled) setWidgetResults([]);
      });
    return () => {
      cancelled = true;
    };
  }, [paletteOpen, paletteQuery, currentOrg]);

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
    const orgCommands: CommandItem[] = (me?.organizations ?? [])
      .filter((org) => org.slug !== currentOrg?.slug)
      .map((org) => ({
        id: `org-${org.slug}`,
        label: `Switch to ${org.name}`,
        group: "Organisations",
        onSelect: () => router.push(`/${org.slug}`),
      }));
    const widgetCommands: CommandItem[] = widgetResults.map((widget) => ({
      id: `widget-${widget.id}`,
      label: widget.name,
      group: "Widgets",
      onSelect: () => router.push(`/${params.org}/widgets/${widget.id}`),
    }));
    const all = [...navCommands, ...orgCommands, ...widgetCommands];
    if (!paletteQuery) return all;
    const query = paletteQuery.toLowerCase();
    return all.filter(
      (item) => item.group === "Widgets" || item.label.toLowerCase().includes(query),
    );
  }, [navItems, me, paletteQuery, router, widgetResults, params.org, currentOrg]);

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
      <ImpersonationBannerHost />
      <AppShell
        logo={
          <Link href="/" className="text-sm font-semibold text-foreground">
            Keel
          </Link>
        }
        orgSwitcher={<OrgSwitcher />}
        nav={nav}
        commandPaletteTrigger={
          <Button
            type="button"
            variant="outline"
            onClick={() => setPaletteOpen(true)}
            className="hidden text-muted-foreground sm:flex"
          >
            <Search />
            Search…
            <Kbd className="ml-2">{isMac ? "⌘K" : "Ctrl K"}</Kbd>
          </Button>
        }
        themeToggle={
          <ThemeToggleButton
            isDark={resolvedTheme === "dark"}
            onToggle={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          />
        }
        accountMenu={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="rounded-full"
                aria-label="Account menu"
              >
                <Avatar>
                  <AvatarFallback>
                    {accountInitials(me?.user.name ?? me?.user.email)}
                  </AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="truncate font-normal text-muted-foreground">
                {me?.user.email}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/account/profile">
                  <User />
                  Profile
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/account/security">
                  <Shield />
                  Security
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/account/sessions">
                  <Settings />
                  Sessions
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={() => void signOut()}>
                <LogOut />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
        jobTraySlot={currentOrg ? <JobTray orgSlug={currentOrg.slug} /> : null}
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
