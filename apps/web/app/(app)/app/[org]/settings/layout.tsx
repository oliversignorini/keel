"use client";

import { PageHeader, Tabs, TabsContent, TabsList, TabsTrigger } from "@keel/ui";
import { useParams, usePathname } from "next/navigation";
import Link from "next/link";

/**
 * Secondary horizontal tab row (PRD §5 "Layout — top bar navigation":
 * "Settings uses a secondary horizontal tab row rather than a nested
 * sidebar"): General · Members · Roles · Billing · Audit. Audit is
 * Phase 8's (docs/plans/phase-8.md 8.2) — the fifth tab PRD §5 lists.
 *
 * The row is a Radix `<Tabs>` whose triggers are `asChild` `<Link>`s:
 * navigation stays real (each tab is a route, middle-clickable and
 * linkable), while the list keeps the roving-tabindex and `aria-selected`
 * semantics a hand-rolled link row never had.
 *
 * The routed `children` MUST stay wrapped in a `<TabsContent>` for the
 * active slug. Radix points every trigger's `aria-controls` at a panel id
 * it expects to exist, and axe (`aria-valid-attr-value`, critical) fails
 * the selected trigger when that panel is absent — verified against
 * axe-core 4.13, the version e2e/app-accessibility.spec.ts runs. Rendering
 * the panel is also the honest description of the markup: the routed page
 * genuinely is the active tab's panel.
 */
const TABS = [
  { slug: "general", label: "General" },
  { slug: "members", label: "Members" },
  { slug: "roles", label: "Roles" },
  { slug: "billing", label: "Billing" },
  { slug: "audit", label: "Audit" },
] as const;

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ org: string }>();
  const pathname = usePathname();

  // The tab is the segment after `/settings`, so a future nested route
  // (`/settings/members/[id]`) still highlights its parent tab.
  const active = TABS.find((tab) => pathname.split("/").includes(tab.slug))?.slug ?? "general";

  return (
    <div>
      <PageHeader title="Settings" />
      <Tabs value={active} className="gap-6">
        <TabsList>
          {TABS.map((tab) => (
            <TabsTrigger key={tab.slug} value={tab.slug} asChild>
              <Link href={`/${params.org}/settings/${tab.slug}`}>{tab.label}</Link>
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={active}>{children}</TabsContent>
      </Tabs>
    </div>
  );
}
