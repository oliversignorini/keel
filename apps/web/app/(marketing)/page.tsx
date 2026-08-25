import Link from "next/link";
import type { Metadata } from "next";

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

/** Restrained on purpose (phase-7.md 7.2): this is a template, and a
 * boilerplate with a strong identity is one every project has to fight.
 * Structure and semantics over decoration — a brand pass replaces
 * packages/ui/theme.css and nothing else should need to change. */
export default function LandingPage() {
  return (
    <main>
      <section className="mx-auto max-w-5xl px-4 py-24 text-center">
        <h1 className="text-4xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100 sm:text-5xl">
          Ship the SaaS parts you would rather not build
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-neutral-600 dark:text-neutral-400">
          Auth, organisations, billing, and a marketing site — a working starting point, not a
          tutorial.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link
            href="/signup"
            className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            Start free trial
          </Link>
          <Link
            href="/pricing"
            className="rounded-md border border-neutral-300 px-5 py-2.5 text-sm font-medium text-neutral-900 dark:border-neutral-700 dark:text-neutral-100"
          >
            See pricing
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 pb-24">
        <ul className="grid gap-8 sm:grid-cols-3">
          {FEATURES.map((feature) => (
            <li key={feature.title}>
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
                {feature.title}
              </h2>
              <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">{feature.body}</p>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
