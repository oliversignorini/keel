import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UnprocessableEntityError } from "./errors";
import { identityFetch } from "./mutator";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("identityFetch", () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    fetchSpy.mockReset();
    vi.stubGlobal("fetch", fetchSpy);
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("always sends credentials: include", async () => {
    fetchSpy.mockResolvedValue(jsonResponse(200, { ok: true }));

    await identityFetch("/_allauth/browser/v1/auth/session");

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("does not attach a CSRF header on GET", async () => {
    fetchSpy.mockResolvedValue(jsonResponse(200, { ok: true }));

    await identityFetch("/_allauth/browser/v1/auth/sessions", { method: "GET" });

    const [, init] = fetchSpy.mock.calls[0]!;
    expect((init.headers as Headers).has("X-CSRFToken")).toBe(false);
  });

  it("attaches the CSRF header from the csrftoken cookie on POST", async () => {
    document.cookie = "csrftoken=abc123; path=/";
    fetchSpy.mockResolvedValue(jsonResponse(200, { ok: true }));

    await identityFetch("/_allauth/browser/v1/auth/login", { method: "POST", body: "{}" });

    const [, init] = fetchSpy.mock.calls[0]!;
    expect((init.headers as Headers).get("X-CSRFToken")).toBe("abc123");
  });

  it("resolves with { data, status, headers } on success", async () => {
    fetchSpy.mockResolvedValue(jsonResponse(200, { status: 200, data: { user: { id: "1" } } }));

    const result = await identityFetch<{ data: unknown; status: number; headers: Headers }>(
      "/_allauth/browser/v1/auth/login",
    );

    expect(result.status).toBe(200);
    expect(result.data).toEqual({ status: 200, data: { user: { id: "1" } } });
    expect(result.headers.get("Content-Type")).toBe("application/json");
  });

  it("throws the matching typed error on a non-2xx response", async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse(422, {
        error: { code: "validation_error", message: "Fix the highlighted fields.", details: [] },
      }),
    );

    await expect(identityFetch("/_allauth/browser/v1/auth/signup", { method: "POST" })).rejects.toBeInstanceOf(
      UnprocessableEntityError,
    );
  });

  it("carries Retry-After through on 429", async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse(
        429,
        { error: { code: "rate_limited", message: "Too many requests." } },
        { "Retry-After": "12" },
      ),
    );

    try {
      await identityFetch("/_allauth/browser/v1/auth/login", { method: "POST" });
      expect.unreachable();
    } catch (error) {
      expect(error).toMatchObject({ status: 429, retryAfterSeconds: 12 });
    }
  });
});
