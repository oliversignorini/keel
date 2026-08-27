import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "./middleware";

function request(url: string, { session = false }: { session?: boolean } = {}): NextRequest {
  const req = new NextRequest(url);
  if (session) {
    req.cookies.set("sessionid", "test-session");
  }
  return req;
}

describe("middleware — docs/adr/0002-auth-bff-shape.md BFF rewrite", () => {
  it("rewrites /_allauth/… to the routable internal allauth handler", () => {
    const response = middleware(request("http://app.lvh.me:3000/_allauth/browser/v1/auth/session"));

    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "http://app.lvh.me:3000/api/internal/allauth/browser/v1/auth/session",
    );
  });

  it("rewrites bare /_allauth with no trailing path", () => {
    const response = middleware(request("http://lvh.me:3000/_allauth"));

    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "http://lvh.me:3000/api/internal/allauth",
    );
  });

  it("does not apply the app-host /app rewrite or auth-guard redirects to /_allauth", () => {
    const response = middleware(request("http://app.lvh.me:3000/_allauth/browser/v1/auth/session"));

    expect(response.status).not.toBe(307);
  });
});

describe("middleware — plan 6.A host-based routing", () => {
  it("rewrites the app host's root to /app internally, keeping the visible URL", () => {
    const response = middleware(request("http://app.lvh.me:3000/", { session: true }));

    expect(response.headers.get("x-middleware-rewrite")).toBe("http://app.lvh.me:3000/app");
  });

  it("rewrites an app-host org path to its /app/[org]/... file path", () => {
    const response = middleware(
      request("http://app.lvh.me:3000/acme/settings/billing", { session: true }),
    );

    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "http://app.lvh.me:3000/app/acme/settings/billing",
    );
  });

  it("leaves /account alone on the app host — no /app prefix to rewrite onto", () => {
    const response = middleware(
      request("http://app.lvh.me:3000/account/profile", { session: true }),
    );

    expect(response.headers.get("x-middleware-rewrite")).toBeNull();
    expect(response.headers.get("location")).toBeNull();
  });

  it("leaves marketing on the apex host untouched", () => {
    const response = middleware(request("http://lvh.me:3000/pricing"));

    expect(response.headers.get("x-middleware-rewrite")).toBeNull();
    expect(response.headers.get("location")).toBeNull();
  });

  it("sends a stray apex /app/* request to its new home on the app host", () => {
    const response = middleware(request("http://lvh.me:3000/app/acme/settings"));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://app.lvh.me:3000/acme/settings");
  });

  it("redirects an unauthenticated app-host visitor to the apex login, with an absolute next=", () => {
    const response = middleware(request("http://app.lvh.me:3000/acme"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location")!);
    expect(location.host).toBe("lvh.me:3000");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("http://app.lvh.me:3000/acme");
  });

  it("redirects an unauthenticated apex /account visitor to /login with a relative next=", () => {
    const response = middleware(request("http://lvh.me:3000/account/security"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location")!);
    expect(location.host).toBe("lvh.me:3000");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/account/security");
  });

  it("lets an authenticated app-host visitor through", () => {
    const response = middleware(request("http://app.lvh.me:3000/acme", { session: true }));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("does not redirect a visitor with a session cookie away from /login (ADR 0002 — lib/auth/route-guard.ts)", () => {
    const response = middleware(request("http://lvh.me:3000/login", { session: true }));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("lets an unauthenticated apex visitor reach /login", () => {
    const response = middleware(request("http://lvh.me:3000/login"));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });
});
