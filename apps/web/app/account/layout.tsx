"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { ImpersonationBannerHost } from "@/components/org/impersonation-banner";
import { Tabs, TabsList, TabsTrigger } from "@keel/ui";

const TABS = [
  { href: "/account/profile", label: "Profile" },
  { href: "/account/security", label: "Security" },
  { href: "/account/sessions", label: "Sessions" },
];

/**
 * Renders outside `<AppShell>` on purpose — account settings
 * aren't scoped to an organisation, so the org switcher and nav have
 * nothing to show here. Still needs the shell's tokens and a way back
 * into the product: a minimal header with the logo and an
 * explicit "Back to app" link, rather than stranding the user on
 * browser Back.
 */
export default function AccountLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const activeTab = TABS.find((tab) => pathname?.startsWith(tab.href))?.href ?? "/account/profile";

  return (
    <div className="min-h-screen bg-background text-foreground">
      <ImpersonationBannerHost />
      <header className="flex h-14 items-center gap-3 border-b border-border px-4">
        <Link href="/" className="text-sm font-semibold text-foreground">
          Keel
        </Link>
        <Link
          href="/app"
          className="ml-auto flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Back to app
        </Link>
      </header>

      <main className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12">
        <h1 className="text-lg font-semibold">Account</h1>
        <Tabs value={activeTab}>
          <TabsList>
            {TABS.map((tab) => (
              <TabsTrigger key={tab.href} value={tab.href} asChild>
                <Link href={tab.href}>{tab.label}</Link>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {children}
      </main>
    </div>
  );
}
