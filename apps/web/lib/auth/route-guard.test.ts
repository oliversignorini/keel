import { describe, expect, it } from "vitest";

import { resolveGuardRedirect } from "./route-guard";

describe("resolveGuardRedirect", () => {
  it("sends an unauthenticated visitor to /app away to /login with next=", () => {
    expect(resolveGuardRedirect("/app/acme", false)).toBe("/login?next=%2Fapp%2Facme");
  });

  it("sends an unauthenticated visitor to /account away to /login with next=", () => {
    expect(resolveGuardRedirect("/account/security", false)).toBe(
      "/login?next=%2Faccount%2Fsecurity",
    );
  });

  it("lets an authenticated visitor through to /app", () => {
    expect(resolveGuardRedirect("/app/acme", true)).toBeNull();
  });

  it("does not redirect a visitor with a session cookie away from /login or /signup (ADR 0002)", () => {
    // A pending, not-yet-authenticated allauth flow (email verification,
    // MFA) sets a real sessionid cookie too — bouncing that visitor away
    // from /login sends them into a page that immediately 401s and
    // bounces them right back, with no way to ever reach the login form.
    // See route-guard.ts's docstring for the full incident.
    expect(resolveGuardRedirect("/login", true)).toBeNull();
    expect(resolveGuardRedirect("/signup", true)).toBeNull();
  });

  it("lets an unauthenticated visitor reach /login", () => {
    expect(resolveGuardRedirect("/login", false)).toBeNull();
  });

  it("leaves unrelated routes alone either way", () => {
    expect(resolveGuardRedirect("/pricing", false)).toBeNull();
    expect(resolveGuardRedirect("/pricing", true)).toBeNull();
  });

  it("treats /app and /account as prefixes, not just exact matches", () => {
    expect(resolveGuardRedirect("/app", false)).toBe("/login?next=%2Fapp");
    expect(resolveGuardRedirect("/accountability", false)).toBeNull();
  });

  it("sends an unauthenticated visitor away from /onboarding to /login with next=", () => {
    expect(resolveGuardRedirect("/onboarding", false)).toBe("/login?next=%2Fonboarding");
  });

  it("lets an authenticated visitor reach /onboarding", () => {
    expect(resolveGuardRedirect("/onboarding", true)).toBeNull();
  });

  it("leaves /invite/[token] unguarded either way — it must work signed out", () => {
    expect(resolveGuardRedirect("/invite/abc123", false)).toBeNull();
    expect(resolveGuardRedirect("/invite/abc123", true)).toBeNull();
  });
});
