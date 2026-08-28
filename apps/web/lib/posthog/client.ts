"use client";

/**
 * PostHog, client-side, with a server-side capture helper for billing
 * events. No project key exists for this project yet —
 * `posthog.init()` without an API key never fires a network request
 * (posthog-js's own documented behaviour: it queues locally and drops),
 * so mounting the provider unconditionally is safe either way. The
 * server-side half is keel/core/posthog.py.
 */
import posthog from "posthog-js";

let initialized = false;

export function initPostHog(): typeof posthog | null {
  if (typeof window === "undefined") return null;
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key) return null;
  if (!initialized) {
    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com",
      // Manual pageview capture (App Router route changes aren't full
      // page loads, so posthog-js's default document-load capture would
      // miss every client-side navigation) — deferred to whichever
      // worktree wires up route-level capture; this only ensures the
      // client never sends events without a key.
      capture_pageview: false,
      person_profiles: "identified_only",
    });
    initialized = true;
  }
  return posthog;
}
