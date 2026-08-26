import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("posthog-js", () => ({
  default: { init: vi.fn() },
}));

import posthog from "posthog-js";

describe("initPostHog", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    vi.mocked(posthog.init).mockClear();
  });

  it("does not call posthog.init without a project key", async () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "");
    const { initPostHog } = await import("./client");

    const result = initPostHog();

    expect(result).toBeNull();
    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("calls posthog.init with the configured key and host", async () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "phc_test_key");
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_HOST", "https://us.i.posthog.com");
    const { initPostHog } = await import("./client");

    const result = initPostHog();

    expect(result).toBe(posthog);
    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test_key",
      expect.objectContaining({ api_host: "https://us.i.posthog.com" }),
    );
  });

  it("only initializes once across repeated calls", async () => {
    vi.stubEnv("NEXT_PUBLIC_POSTHOG_KEY", "phc_test_key");
    const { initPostHog } = await import("./client");

    initPostHog();
    initPostHog();

    expect(posthog.init).toHaveBeenCalledTimes(1);
  });
});
