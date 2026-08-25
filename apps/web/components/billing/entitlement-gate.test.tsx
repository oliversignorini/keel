import { PaymentRequiredError, UnauthorizedError } from "@keel/api-client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EntitlementGate, useReportEntitlementError } from "./entitlement-gate";

const useOrgContextMock = vi.fn();
const listPlansMock = vi.fn();

vi.mock("@/lib/org/org-context", () => ({
  useOrgContext: () => useOrgContextMock(),
}));

vi.mock("@/lib/billing/api", () => ({
  listPlans: () => listPlansMock(),
}));

const PLANS = [
  {
    id: "plan-free",
    code: "free",
    name: "Free",
    sort_order: 0,
    entitlements: { features: [] },
    prices: [{ id: "p1", interval: "month", unit_amount: 0, currency: "AUD" }],
  },
  {
    id: "plan-pro",
    code: "pro",
    name: "Pro",
    sort_order: 1,
    entitlements: { features: ["api_access"] },
    prices: [{ id: "p2", interval: "month", unit_amount: 1900, currency: "AUD" }],
  },
  {
    id: "plan-scale",
    code: "scale",
    name: "Scale",
    sort_order: 2,
    entitlements: { features: ["api_access", "sso"] },
    prices: [{ id: "p3", interval: "month", unit_amount: 9900, currency: "AUD" }],
  },
];

function orgWithFeatures(features: string[]) {
  useOrgContextMock.mockReturnValue({
    loading: false,
    currentOrg: { slug: "acme", entitlements: { features, limits: {} }, permissions: [] },
  });
}

/** A wrapped action doing what a real one would: call the API, and hand
 * whatever it caught to the surrounding gate. */
function GatedAction({ error }: { error: unknown }) {
  const report = useReportEntitlementError();
  return (
    <button
      type="button"
      onClick={() => {
        report(error);
      }}
    >
      Call API
    </button>
  );
}

beforeEach(() => {
  useOrgContextMock.mockReset();
  listPlansMock.mockReset();
  listPlansMock.mockResolvedValue(PLANS);
});

describe("<EntitlementGate>", () => {
  it("renders children when the organisation's entitlements include the feature", async () => {
    orgWithFeatures(["api_access"]);

    render(
      <EntitlementGate feature="api_access">
        <button>Use the API</button>
      </EntitlementGate>,
    );

    expect(screen.getByRole("button", { name: "Use the API" })).toBeInTheDocument();
    // The entitled path costs no catalogue request.
    expect(listPlansMock).not.toHaveBeenCalled();
  });

  it("renders an upgrade prompt naming the cheapest plan that grants the feature", async () => {
    orgWithFeatures([]);

    render(
      <EntitlementGate feature="api_access">
        <button>Use the API</button>
      </EntitlementGate>,
    );

    expect(screen.queryByRole("button", { name: "Use the API" })).not.toBeInTheDocument();
    // Pro and Scale both grant api_access; the prompt names the entry one.
    expect(await screen.findByText("Available on the Pro plan.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upgrade to Pro" })).toHaveAttribute(
      "href",
      "/app/acme/settings/billing",
    );
  });

  it("falls back to a generic prompt when no plan grants the feature", async () => {
    orgWithFeatures([]);

    render(
      <EntitlementGate feature="time_travel">
        <button>Use the API</button>
      </EntitlementGate>,
    );

    expect(await screen.findByText("Available on a paid plan.")).toBeInTheDocument();
  });

  it("renders a caller-supplied fallback instead of the prompt", () => {
    orgWithFeatures([]);

    render(
      <EntitlementGate feature="api_access" fallback={<span>Not included</span>}>
        <button>Use the API</button>
      </EntitlementGate>,
    );

    expect(screen.getByText("Not included")).toBeInTheDocument();
    expect(screen.queryByText(/Available on/)).not.toBeInTheDocument();
  });

  it("closes on a 402 reported from inside, even though /me said the feature was entitled", async () => {
    // The stale-entitlements case: the trial ended, or another admin
    // downgraded, after this page loaded. The API is the enforcement
    // point and it has just said so.
    orgWithFeatures(["api_access"]);
    const error = new PaymentRequiredError({
      code: "feature_not_entitled",
      message: "Your plan does not include 'api_access'.",
      details: { feature: "api_access" } as never,
    });

    render(
      <EntitlementGate feature="api_access">
        <GatedAction error={error} />
      </EntitlementGate>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Call API" }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Call API" })).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("Available on the Pro plan.")).toBeInTheDocument();
  });

  it("closes on a 402 whose details name no feature at all", async () => {
    orgWithFeatures(["api_access"]);
    const error = new PaymentRequiredError({ code: "payment_required", message: "Nope." });

    render(
      <EntitlementGate feature="api_access">
        <GatedAction error={error} />
      </EntitlementGate>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Call API" }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Call API" })).not.toBeInTheDocument(),
    );
  });

  it("ignores a 402 belonging to a different feature", async () => {
    orgWithFeatures(["api_access"]);
    const error = new PaymentRequiredError({
      code: "limit_exceeded",
      message: "Too many widgets.",
      details: { resource: "widgets", limit: 3 } as never,
    });

    render(
      <EntitlementGate feature="api_access">
        <GatedAction error={error} />
      </EntitlementGate>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Call API" }));

    expect(screen.getByRole("button", { name: "Call API" })).toBeInTheDocument();
  });

  it("ignores an error that is not a 402", async () => {
    orgWithFeatures(["api_access"]);
    const error = new UnauthorizedError({ code: "unauthorized", message: "Sign in." });

    render(
      <EntitlementGate feature="api_access">
        <GatedAction error={error} />
      </EntitlementGate>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Call API" }));

    expect(screen.getByRole("button", { name: "Call API" })).toBeInTheDocument();
  });

  it("renders nothing while /me is still loading", () => {
    useOrgContextMock.mockReturnValue({ loading: true, currentOrg: null });

    const { container } = render(
      <EntitlementGate feature="api_access">
        <button>Use the API</button>
      </EntitlementGate>,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("useReportEntitlementError outside a gate", () => {
  it("returns false rather than throwing, so a shared action can call it unconditionally", async () => {
    const error = new PaymentRequiredError({ code: "payment_required", message: "Nope." });
    let result: boolean | null = null;

    function Ungated() {
      const report = useReportEntitlementError();
      return (
        <button
          type="button"
          onClick={() => {
            result = report(error);
          }}
        >
          Call API
        </button>
      );
    }

    render(<Ungated />);
    fireEvent.click(screen.getByRole("button", { name: "Call API" }));

    expect(result).toBe(false);
  });
});
