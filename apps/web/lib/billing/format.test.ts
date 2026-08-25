import { describe, expect, it } from "vitest";
import { formatDate, formatPrice } from "./format";

// These assertions are locale-pinned on purpose: if the locale stops being
// pinned, the value differs between the Node render and the browser render
// and React reports a hydration mismatch on the statically-rendered pricing
// page. Asserting the exact string is what catches that regression.
describe("formatPrice", () => {
  // "$29", not "A$29": in en-AU the Australian dollar is the *local*
  // currency, so CLDR prints a bare "$". en-US treats it as foreign and
  // disambiguates to "A$". That difference is exactly the hydration
  // mismatch this pin exists to remove.
  it("formats AUD identically regardless of the runtime's own locale", () => {
    expect(formatPrice(2900, "AUD")).toBe("$29");
  });

  it("shows cents only when the amount has them", () => {
    expect(formatPrice(2950, "AUD")).toBe("$29.50");
  });

  // Intl does not throw on an unknown code, it prints the code itself.
  // Asserted so the unreachable catch branch below is not mistaken for
  // the thing keeping this safe.
  it("degrades instead of throwing on an unknown currency", () => {
    //  , not a plain space: Intl separates an unknown currency code
    // from the number with a non-breaking space.
    expect(formatPrice(2900, "ZZZ")).toBe("ZZZ 29");
  });
});

describe("formatDate", () => {
  it("formats in the pinned locale", () => {
    expect(formatDate("2026-03-09T00:00:00Z")).toBe("9 March 2026");
  });

  it("returns the input unchanged when it is not a date", () => {
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });
});
