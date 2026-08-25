import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DunningBanner } from "./dunning-banner";
import { TrialBanner } from "./trial-banner";
import type { Subscription } from "@/lib/billing/types";

vi.mock("@/lib/org/org-context", () => ({
  useOrgContext: () => ({ currentOrg: { permissions: ["billing.manage"] } }),
}));

function subscription(overrides: Partial<Subscription> = {}): Subscription {
  return {
    id: "sub-1",
    plan: "pro",
    status: "active",
    quantity: 3,
    current_period_end: "2026-09-01T00:00:00Z",
    trial_end: null,
    cancel_at_period_end: false,
    ...overrides,
  };
}

describe("<TrialBanner>", () => {
  it("names the trial end date while the subscription is trialing", () => {
    render(
      <TrialBanner
        subscription={subscription({ status: "trialing", trial_end: "2026-09-09T00:00:00Z" })}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(/Your trial ends 9 September 2026/);
  });

  it("renders nothing in any other status, even with a trial_end still set", () => {
    // Stripe leaves trial_end populated after the trial converts — the
    // status is the trigger, not the date.
    const { container } = render(
      <TrialBanner
        subscription={subscription({ status: "active", trial_end: "2026-09-09T00:00:00Z" })}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing without a subscription", () => {
    const { container } = render(<TrialBanner subscription={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("<DunningBanner>", () => {
  it("appears when the subscription is past_due, without threatening loss of access", () => {
    render(<DunningBanner subscription={subscription({ status: "past_due" })} orgSlug="acme" />);

    // phase-4.md B.6: dunning does not revoke access, and the copy must
    // not claim otherwise.
    expect(screen.getByRole("alert")).toHaveTextContent(/Your organisation keeps working/);
    expect(screen.getByRole("link", { name: "Update payment details" })).toHaveAttribute(
      "href",
      "/app/acme/settings/billing",
    );
  });

  it("renders nothing while the subscription is healthy", () => {
    const { container } = render(
      <DunningBanner subscription={subscription({ status: "active" })} orgSlug="acme" />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
