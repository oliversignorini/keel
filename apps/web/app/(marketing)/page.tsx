import Link from "next/link";
import type { Metadata } from "next";
import { buttonVariants } from "@keel/ui";

import { JsonLd } from "@/components/json-ld";
import { SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Keel — Django + Next.js SaaS template",
  description:
    "A production-shaped SaaS starting point: auth, organisations, billing, and a marketing site, wired together and ready to rebrand.",
};

const FEATURES = [
  {
    title: "Auth that's actually finished",
    body: "Email/password, Google, MFA, invitations and sessions — built on django-allauth's headless API, not reimplemented.",
  },
  {
    title: "Multi-tenant from day one",
    body: "Organisations, roles, and permissions, with a switcher that keeps tenant context visible everywhere.",
  },
  {
    title: "Billing wired to Stripe",
    body: "Checkout, the customer portal, webhooks, and entitlement gates that read live from your plan configuration.",
  },
];

/** Restrained on purpose: this is a template, and a
 * boilerplate with a strong identity is one every project has to fight.
 * Structure and semantics over decoration — a brand pass replaces
 * packages/ui/theme.css and nothing else should need to change. */
export default function LandingPage() {
  return (
    <main>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Organization",
          name: "Keel",
          url: SITE_URL,
        }}
      />
      <section className="mx-auto max-w-5xl px-4 py-24 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
          Ship the SaaS parts you would rather not build
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
          Auth, organisations, billing, and a marketing site — a working starting point, not a
          tutorial.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link href="/signup" className={buttonVariants({ size: "lg" })}>
            Start free trial
          </Link>
          <Link href="/pricing" className={buttonVariants({ variant: "outline", size: "lg" })}>
            See pricing
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 pb-24">
        <ul className="grid gap-8 sm:grid-cols-3">
          {FEATURES.map((feature) => (
            <li key={feature.title}>
              <h2 className="text-lg font-semibold text-foreground">{feature.title}</h2>
              <p className="mt-2 text-sm text-muted-foreground">{feature.body}</p>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
