import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { proxyRequest } from "./proxy";

function upstreamJson(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("proxyRequest", () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    fetchSpy.mockReset();
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards method, query string, and body to the upstream origin", async () => {
    fetchSpy.mockResolvedValue(upstreamJson(200, { ok: true }));
    const request = new NextRequest("http://app.lvh.me:3000/api/v1/orgs/acme/widgets/?limit=5", {
      method: "POST",
      body: JSON.stringify({ name: "widget" }),
      headers: { "Content-Type": "application/json", Cookie: "sessionid=abc" },
    });

    await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/api/v1/orgs/acme/widgets/",
    });

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toBe("http://api.lvh.me:8000/api/v1/orgs/acme/widgets/?limit=5");
    expect(init.method).toBe("POST");
    expect((init.headers as Headers).get("Cookie")).toBe("sessionid=abc");
    // Buffered as a Blob, not streamed (see proxy.ts) — Django's dev
    // server doesn't decode a chunked-transfer-encoded request body.
    // jsdom's Blob (this test environment) doesn't interoperate with a
    // real Response/fetch body reader the way Node's does, so this checks
    // shape/size rather than round-tripping the content through `.text()`.
    const body = init.body as Blob;
    expect(body.constructor.name).toBe("Blob");
    expect(body.size).toBe(JSON.stringify({ name: "widget" }).length);
  });

  it("does not attach a body on GET", async () => {
    fetchSpy.mockResolvedValue(upstreamJson(200, { ok: true }));
    const request = new NextRequest("http://app.lvh.me:3000/api/v1/me/");

    await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/api/v1/me/",
    });

    const [, init] = fetchSpy.mock.calls[0]!;
    expect(init.body).toBeUndefined();
    expect(init.duplex).toBeUndefined();
  });

  it("strips hop-by-hop headers before forwarding", async () => {
    fetchSpy.mockResolvedValue(upstreamJson(200, { ok: true }));
    const request = new NextRequest("http://app.lvh.me:3000/api/v1/me/", {
      headers: { Connection: "keep-alive", Host: "app.lvh.me:3000" },
    });

    await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/api/v1/me/",
    });

    const [, init] = fetchSpy.mock.calls[0]!;
    const headers = init.headers as Headers;
    expect(headers.has("Connection")).toBe(false);
    expect(headers.has("Host")).toBe(false);
  });

  it("strips client-asserted X-Forwarded-* headers so a browser cannot spoof its own identity", async () => {
    // Django's anon rate limiting can be configured to key its bucket off
    // X-Forwarded-For, and prod's SECURE_PROXY_SSL_HEADER trusts
    // X-Forwarded-Proto — both would be caller-controlled if this proxy
    // forwarded what the browser sent.
    fetchSpy.mockResolvedValue(upstreamJson(200, { ok: true }));
    const request = new NextRequest("http://app.lvh.me:3000/api/v1/me/", {
      headers: {
        "X-Forwarded-For": "1.2.3.4",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "evil.example.com",
        "X-Forwarded-Port": "443",
        "X-Real-IP": "1.2.3.4",
        Forwarded: "for=1.2.3.4;proto=https",
        Cookie: "sessionid=abc",
      },
    });

    await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/api/v1/me/",
    });

    const headers = fetchSpy.mock.calls[0]![1].headers as Headers;
    for (const name of [
      "x-forwarded-for",
      "x-forwarded-proto",
      "x-forwarded-host",
      "x-forwarded-port",
      "x-real-ip",
      "forwarded",
    ]) {
      expect(headers.has(name)).toBe(false);
    }
    // Everything else still rides along.
    expect(headers.get("Cookie")).toBe("sessionid=abc");
  });

  it("relays every Set-Cookie header individually — Django often sets two in one response", async () => {
    const upstream = upstreamJson(200, { ok: true });
    upstream.headers.append("Set-Cookie", "sessionid=new; Path=/; HttpOnly");
    upstream.headers.append("Set-Cookie", "csrftoken=xyz; Path=/");
    fetchSpy.mockResolvedValue(upstream);
    const request = new NextRequest("http://app.lvh.me:3000/_allauth/browser/v1/auth/session");

    const response = await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/_allauth/browser/v1/auth/session",
    });

    expect(response.headers.getSetCookie()).toEqual([
      "sessionid=new; Path=/; HttpOnly",
      "csrftoken=xyz; Path=/",
    ]);
  });

  it("relays a 3xx response untouched when there is no transformErrorBody — the OAuth provider-redirect path", async () => {
    fetchSpy.mockResolvedValue(
      new Response(null, {
        status: 302,
        headers: { Location: "https://accounts.google.com/o/oauth2/v2/auth" },
      }),
    );
    const request = new NextRequest(
      "http://app.lvh.me:3000/_allauth/browser/v1/auth/provider/redirect",
      {
        method: "POST",
        body: "provider=google",
      },
    );

    const response = await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/_allauth/browser/v1/auth/provider/redirect",
    });

    expect(response.status).toBe(302);
    expect(response.headers.get("Location")).toBe("https://accounts.google.com/o/oauth2/v2/auth");
    const [, init] = fetchSpy.mock.calls[0]!;
    expect(init.redirect).toBe("manual");
  });

  it("passes a Keel-shaped error body through unchanged when transformErrorBody is omitted", async () => {
    fetchSpy.mockResolvedValue(
      upstreamJson(403, { error: { code: "insufficient_role", message: "Nope." } }),
    );
    const request = new NextRequest("http://app.lvh.me:3000/api/v1/orgs/acme/widgets/");

    const response = await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/api/v1/orgs/acme/widgets/",
    });

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({
      error: { code: "insufficient_role", message: "Nope." },
    });
  });

  it("re-emits an allauth field-error response as Keel's own envelope via transformErrorBody", async () => {
    fetchSpy.mockResolvedValue(
      upstreamJson(400, {
        status: 400,
        errors: [{ code: "email_taken", param: "email", message: "Already registered." }],
      }),
    );
    const request = new NextRequest("http://app.lvh.me:3000/_allauth/browser/v1/auth/signup", {
      method: "POST",
    });

    const response = await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/_allauth/browser/v1/auth/signup",
      transformErrorBody: (_status, body) => {
        const allauthBody = body as { errors: Array<{ code: string; message: string }> };
        const [first] = allauthBody.errors;
        return { code: first!.code, message: first!.message };
      },
    });

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({
      error: { code: "email_taken", message: "Already registered." },
    });
  });

  it("does not run transformErrorBody on a 2xx response", async () => {
    fetchSpy.mockResolvedValue(
      upstreamJson(200, { status: 200, data: { is_authenticated: true } }),
    );
    const request = new NextRequest("http://app.lvh.me:3000/_allauth/browser/v1/auth/session");
    const transformErrorBody = vi.fn();

    await proxyRequest(request, {
      upstreamOrigin: "http://api.lvh.me:8000",
      upstreamPath: "/_allauth/browser/v1/auth/session",
      transformErrorBody,
    });

    expect(transformErrorBody).not.toHaveBeenCalled();
  });
});
