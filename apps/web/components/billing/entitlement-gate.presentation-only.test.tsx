import { PaymentRequiredError } from "@keel/api-client";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EntitlementGate } from "./entitlement-gate";
import { createInvitation } from "@/lib/org/api";

/**
 * phase-4.md Worktree C, the load-bearing one: "The client renders from
 * the permission and entitlement lists in `/me`. It is never the
 * enforcement point. Removing a gate client-side must still yield 402
 * from the API — test that."
 *
 * This is the entitlement twin of e2e/org-permissions.spec.ts (which
 * proves the same thing for `<Can>` and 403, against a live server). It
 * runs at the transport layer instead: a real API call, through the real
 * `identityFetch` mutator and the real error mapping, with **no gate
 * anywhere in the tree** — the exact situation of someone deleting the
 * component from the DOM or calling `fetch` from the console. The server
 * answers 402 regardless, and the client turns that into a
 * `PaymentRequiredError` the caller cannot mistake for success.
 *
 * The endpoint used is invitations, because the seat limit is the one
 * entitlement the PRD's acceptance list names as a live 402 ("Adding a
 * member beyond the seat entitlement returns 402 with upgrade context").
 * The proof that the *server* actually raises it lives where it belongs,
 * in apps/api/keel/billing/tests/test_entitlements.py — `check_feature`
 * and `check_limit` raise `PaymentRequired` with no client in the picture
 * at all. What is asserted here is the client half: a hidden gate, a
 * removed gate, and no gate are all worth exactly the same.
 */

const useOrgContextMock = vi.fn();

vi.mock("@/lib/org/org-context", () => ({
  useOrgContext: () => useOrgContextMock(),
}));

vi.mock("@/lib/billing/api", () => ({
  listPlans: () => Promise.resolve([]),
}));

const SEAT_LIMIT_402 = {
  error: {
    code: "limit_exceeded",
    message: "This would exceed your plan's seats limit (3).",
    details: { resource: "seats", limit: 3, current_usage: 3 },
  },
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  useOrgContextMock.mockReturnValue({
    loading: false,
    currentOrg: { slug: "acme", entitlements: { features: [], limits: {} }, permissions: [] },
  });
  // A csrftoken already present skips the mutator's priming request, so
  // the only fetch below is the one under test.
  document.cookie = "csrftoken=test-token";
  fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(SEAT_LIMIT_402), {
      status: 402,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("<EntitlementGate> is presentation only", () => {
  it("hides the action — and the API 402s just the same when the gate is gone", async () => {
    // 1. With the gate, the action is not in the DOM at all.
    const gated = render(
      <EntitlementGate feature="seats" fallback={<span>Upgrade required</span>}>
        <button>Invite a teammate</button>
      </EntitlementGate>,
    );
    expect(screen.queryByRole("button", { name: "Invite a teammate" })).not.toBeInTheDocument();
    gated.unmount();

    // 2. Now do what removing the gate does: make the request anyway.
    await expect(
      createInvitation("acme", { email: "x@example.com", role_id: "r1" }),
    ).rejects.toThrow(PaymentRequiredError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("gives the caller the upgrade context the API sent, not a bare failure", async () => {
    // PRD §8 Phase 4: "returns 402 with upgrade context" — the client must
    // surface *what* is over, which is what the gate's prompt and a
    // caller's error message are both built from.
    const error = await createInvitation("acme", {
      email: "x@example.com",
      role_id: "r1",
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(PaymentRequiredError);
    expect((error as PaymentRequiredError).status).toBe(402);
    expect((error as PaymentRequiredError).code).toBe("limit_exceeded");
    expect((error as PaymentRequiredError).details).toMatchObject({ resource: "seats", limit: 3 });
  });
});
