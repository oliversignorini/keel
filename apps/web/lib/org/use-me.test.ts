import { UnauthorizedError } from "@keel/api-client";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "./api";
import { useMe } from "./use-me";

vi.mock("./api", () => ({ getMe: vi.fn() }));

describe("useMe", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    Object.defineProperty(window, "location", {
      value: {
        ...originalLocation,
        href: "http://app.lvh.me:3000/acme",
        host: "app.lvh.me:3000",
        protocol: "http:",
      },
      writable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", { value: originalLocation, writable: true });
    vi.resetAllMocks();
  });

  it("sends a 401 to the apex login with the app-host URL as next=", async () => {
    vi.mocked(getMe).mockRejectedValue(
      new UnauthorizedError({ code: "not_authenticated", message: "" }),
    );

    renderHook(() => useMe());

    await waitFor(() => {
      expect(window.location.href).toBe(
        "http://lvh.me:3000/login?next=" + encodeURIComponent("http://app.lvh.me:3000/acme"),
      );
    });
  });

  it("sets me from a successful response", async () => {
    const me = {
      user: { id: "1", email: "a@example.com", name: "A" },
      organizations: [],
      impersonator: null,
    };
    vi.mocked(getMe).mockResolvedValue(me);

    const { result } = renderHook(() => useMe());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(result.current.me).toEqual(me);
  });
});
