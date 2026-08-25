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

  it("sends an authenticated visitor away from /login", () => {
    expect(resolveGuardRedirect("/login", true)).toBe("/app");
  });

  it("sends an authenticated visitor away from /signup", () => {
    expect(resolveGuardRedirect("/signup", true)).toBe("/app");
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
