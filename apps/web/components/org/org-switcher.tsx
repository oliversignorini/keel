"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Check, ChevronsUpDown, Plus, Search } from "lucide-react";

import { cn } from "@/lib/cn";
import { toApexHost } from "@/lib/host";
import { useOrgContext } from "@/lib/org/org-context";
import { Button, Input, Popover, PopoverContent, PopoverTrigger, Skeleton } from "@keel/ui";

/**
 * Dropdown with create-new (keel-prd.md §5 component inventory), placed
 * immediately after the logo in app/(app)/layout.tsx so tenant context is
 * always visible (§5 "Layout — top bar navigation").
 *
 * Built on `<Popover>` rather than shadcn's `<Command>` — `@keel/ui`'s
 * barrel re-exports `CommandItem` as a type only (it's shadowed by
 * `CommandPalette`'s own `CommandItem` type of the same name), so the
 * `cmdk`-backed item component isn't reachable from here. A filterable
 * button list gets the same result (search, keyboard nav via native
 * focus order, `<Popover>`'s built-in Escape/outside-click) without a
 * second `cmdk` dependency in `apps/web`; flagged for Slice A to give
 * the primitive a distinct export name.
 *
 * Switching organisation pushes the new `/app/[org]` route and lets
 * `<OrgProvider>` refetch `/api/v1/me/` for it (phase-3.md: "Switching
 * organisation updates the route and refetches all data") — no client
 * state carries over between organisations.
 */
export function OrgSwitcher() {
  const router = useRouter();
  const { me, currentOrg } = useOrgContext();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!me) return [];
    const q = query.trim().toLowerCase();
    if (!q) return me.organizations;
    return me.organizations.filter((org) => org.name.toLowerCase().includes(q));
  }, [me, query]);

  if (!me) {
    return <Skeleton className="h-8 w-32" />;
  }

  function switchTo(slug: string) {
    setOpen(false);
    setQuery("");
    // Same host (the app host rewrites bare org paths internally to
    // /app/[org]/... — plan 6.A), so a plain client-side push is enough.
    router.push(`/${slug}`);
  }

  function createOrganisation() {
    setOpen(false);
    // /onboarding is an (auth) route, reachable only on the apex — a
    // cross-host jump needs a real navigation, not router.push.
    window.location.href = `${window.location.protocol}//${toApexHost(window.location.host)}/onboarding`;
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          role="combobox"
          aria-expanded={open}
          className="max-w-[10rem] justify-between gap-1.5 px-2 sm:max-w-[16rem]"
        >
          <span className="flex min-w-0 items-center gap-1.5">
            <Building2 className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{currentOrg?.name ?? "Select organisation"}</span>
          </span>
          <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-2">
        <div className="relative mb-2">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find organisation…"
            className="pl-8"
            autoFocus
          />
        </div>
        <div
          role="listbox"
          aria-label="Organisations"
          className="flex max-h-64 flex-col gap-0.5 overflow-y-auto"
        >
          {filtered.length === 0 ? (
            <p className="px-2 py-3 text-center text-sm text-muted-foreground">
              No organisations found.
            </p>
          ) : (
            filtered.map((org) => (
              <button
                key={org.id}
                type="button"
                role="option"
                aria-selected={org.slug === currentOrg?.slug}
                onClick={() => switchTo(org.slug)}
                className={cn(
                  "flex items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground",
                  org.slug === currentOrg?.slug && "font-medium",
                )}
              >
                <Building2 className="size-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{org.name}</span>
                {org.slug === currentOrg?.slug ? (
                  <Check className="ml-auto size-4 shrink-0" />
                ) : null}
              </button>
            ))
          )}
        </div>
        <div className="mt-1 border-t border-border pt-1">
          <button
            type="button"
            onClick={createOrganisation}
            className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <Plus className="size-4 shrink-0" />
            Create organisation
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
