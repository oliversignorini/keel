import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PricingTable } from "./pricing-table";
import type { PlanWithPrices } from "@/lib/billing/types";

const PLANS = [
  {
    id: "plan-starter",
    code: "starter",
    name: "Starter",
    sort_order: 0,
    entitlements: { features: ["api_access"] },
    prices: [
      { id: "price-starter-m", interval: "month", unit_amount: 1900, currency: "AUD" },
      { id: "price-starter-y", interval: "year", unit_amount: 19000, currency: "AUD" },
    ],
  },
  {
    id: "plan-monthly-only",
    code: "solo",
    name: "Solo",
    sort_order: 1,
    entitlements: {},
    prices: [{ id: "price-solo-m", interval: "month", unit_amount: 900, currency: "AUD" }],
  },
] as unknown as PlanWithPrices[];

describe("<PricingTable>", () => {
  it("shows monthly prices by default", () => {
    render(<PricingTable plans={PLANS} />);

    expect(screen.getByText("$19")).toBeInTheDocument();
    expect(screen.getByText("$9")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Monthly" })).toHaveAttribute("aria-pressed", "true");
  });

  it("switches to the annual price for each plan when toggled", () => {
    render(<PricingTable plans={PLANS} />);

    fireEvent.click(screen.getByRole("button", { name: "Annual" }));

    expect(screen.getByText("$190")).toBeInTheDocument();
    expect(screen.getByText("/ year")).toBeInTheDocument();
  });

  it("hides a plan with no price at the selected interval rather than misquoting it", () => {
    render(<PricingTable plans={PLANS} />);
    expect(screen.getByText("Solo")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Annual" }));

    expect(screen.queryByText("Solo")).not.toBeInTheDocument();
    expect(screen.getByText("Starter")).toBeInTheDocument();
  });

  it("lists the features a plan's entitlements grant as human labels, not raw codes", () => {
    render(<PricingTable plans={PLANS} />);

    expect(screen.getByText("API access")).toBeInTheDocument();
    expect(screen.queryByText("api_access")).not.toBeInTheDocument();
  });

  it("says so when nothing is purchasable on an interval", () => {
    render(<PricingTable plans={[PLANS[1]!]} />);

    fireEvent.click(screen.getByRole("button", { name: "Annual" }));

    expect(
      screen.getByText("No plans are available on this billing interval."),
    ).toBeInTheDocument();
  });
});
