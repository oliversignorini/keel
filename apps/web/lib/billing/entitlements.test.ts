import { describe, expect, it } from "vitest";

import { cheapestPlanWithFeature, hasFeature, readEntitlements } from "./entitlements";
import type { PlanWithPrices } from "./types";
import type { MeOrganization } from "@/lib/org/types";

function org(entitlements: unknown): MeOrganization {
  return {
    id: "org-1",
    slug: "acme",
    name: "Acme",
    role: "Owner",
    permissions: [],
    entitlements: entitlements as Record<string, unknown>,
  };
}

function plan(
  name: string,
  features: string[],
  prices: { interval: string; unit_amount: number }[],
  sortOrder = 0,
): PlanWithPrices {
  return {
    id: `plan-${name}`,
    code: name.toLowerCase(),
    name,
    sort_order: sortOrder,
    entitlements: { features },
    prices: prices.map((price, index) => ({
      id: `${name}-${index}`,
      currency: "AUD",
      ...price,
    })),
  } as unknown as PlanWithPrices;
}

describe("readEntitlements", () => {
  it("narrows the /me blob", () => {
    expect(readEntitlements(org({ features: ["api_access"], limits: { seats: 5 } }))).toEqual({
      features: ["api_access"],
      limits: { seats: 5 },
    });
  });

  it("treats an unsubscribed organisation as empty rather than as an error", () => {
    // resolve_entitlements returns exactly this for an org with no
    // Subscription row (billing/entitlements.py).
    expect(readEntitlements(org({ features: [], limits: {} }))).toEqual({
      features: [],
      limits: {},
    });
    expect(readEntitlements(null)).toEqual({ features: [], limits: {} });
    expect(readEntitlements(org({}))).toEqual({ features: [], limits: {} });
    expect(readEntitlements(org({ features: "nonsense" }))).toEqual({ features: [], limits: {} });
  });
});

describe("hasFeature", () => {
  it("is true only for a feature the plan actually grants", () => {
    const acme = org({ features: ["api_access"], limits: {} });
    expect(hasFeature(acme, "api_access")).toBe(true);
    expect(hasFeature(acme, "sso")).toBe(false);
    expect(hasFeature(null, "api_access")).toBe(false);
  });
});

describe("cheapestPlanWithFeature", () => {
  const free = plan("Free", [], [{ interval: "month", unit_amount: 0 }], 0);
  const pro = plan("Pro", ["api_access"], [{ interval: "month", unit_amount: 1900 }], 1);
  const scale = plan("Scale", ["api_access", "sso"], [{ interval: "month", unit_amount: 9900 }], 2);

  it("names the entry plan that unlocks the feature, not the first one listed", () => {
    expect(cheapestPlanWithFeature([scale, pro, free], "api_access")?.name).toBe("Pro");
  });

  it("compares on the annual price when a plan has no monthly one", () => {
    const annualOnly = plan("Annual", ["sso"], [{ interval: "year", unit_amount: 1000 }], 5);
    expect(cheapestPlanWithFeature([scale, annualOnly], "sso")?.name).toBe("Annual");
  });

  it("breaks a price tie on sort_order", () => {
    const a = plan("A", ["sso"], [{ interval: "month", unit_amount: 1000 }], 9);
    const b = plan("B", ["sso"], [{ interval: "month", unit_amount: 1000 }], 1);
    expect(cheapestPlanWithFeature([a, b], "sso")?.name).toBe("B");
  });

  it("returns null rather than inventing a plan name", () => {
    expect(cheapestPlanWithFeature([free, pro], "time_travel")).toBeNull();
    expect(cheapestPlanWithFeature([], "api_access")).toBeNull();
  });
});
