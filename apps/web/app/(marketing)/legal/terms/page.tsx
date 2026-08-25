import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service — Keel",
};

/** Placeholder copy — every project ships its own terms. This route
 * exists so the shape (route, layout, static rendering) is in place. */
export default function TermsPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-semibold text-neutral-900 dark:text-neutral-100">
        Terms of Service
      </h1>
      <p className="mt-4 text-neutral-600 dark:text-neutral-400">
        Replace this page with your own terms of service before launch.
      </p>
    </main>
  );
}
