import { describe, expect, it, vi } from "vitest";

vi.mock("@keel/api-client", () => ({
  listAuditLogs: vi.fn(),
}));

import { listAuditLogs as generatedListAuditLogs } from "@keel/api-client";
import { listAuditLogs } from "@/lib/org/api";

describe("listAuditLogs", () => {
  it("extracts the cursor query param from a full next URL", async () => {
    vi.mocked(generatedListAuditLogs).mockResolvedValueOnce({
      data: {
        results: [],
        next: "https://api.acme.com/api/v1/orgs/acme/audit/?cursor=abc123",
        previous: null,
      },
    } as never);

    const page = await listAuditLogs("acme");

    expect(page.next).toBe("abc123");
  });

  it("returns null when there is no next page", async () => {
    vi.mocked(generatedListAuditLogs).mockResolvedValueOnce({
      data: { results: [], next: null, previous: null },
    } as never);

    const page = await listAuditLogs("acme");

    expect(page.next).toBeNull();
  });

  it("passes an explicit cursor through to the generated function", async () => {
    vi.mocked(generatedListAuditLogs).mockResolvedValueOnce({
      data: { results: [], next: null, previous: null },
    } as never);

    await listAuditLogs("acme", "abc123");

    expect(generatedListAuditLogs).toHaveBeenCalledWith("acme", { cursor: "abc123" });
  });
});
