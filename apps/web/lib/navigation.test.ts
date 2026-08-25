import { describe, expect, it, vi } from "vitest";

import { navigateTo } from "./navigation";

describe("navigateTo", () => {
  it("uses router.push for a relative path", () => {
    const push = vi.fn();
    navigateTo({ push }, "/app/acme");
    expect(push).toHaveBeenCalledWith("/app/acme");
  });

  it("uses router.push for an absolute same-origin URL", () => {
    const push = vi.fn();
    navigateTo({ push }, `${window.location.origin}/mfa`);
    expect(push).toHaveBeenCalledWith(`${window.location.origin}/mfa`);
  });

  it("does a full navigation for a cross-origin URL (plan 6.A: apex <-> app host)", () => {
    const push = vi.fn();
    const original = window.location;
    // jsdom's window.location isn't directly assignable; replace it for
    // this test only, restored in the finally block.
    Object.defineProperty(window, "location", {
      value: { ...original, href: original.href, origin: original.origin },
      writable: true,
    });

    try {
      navigateTo({ push }, "http://app.lvh.me:3000/acme");
      expect(window.location.href).toBe("http://app.lvh.me:3000/acme");
      expect(push).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, "location", { value: original, writable: true });
    }
  });
});
