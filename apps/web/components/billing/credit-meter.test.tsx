import { NotFoundError } from "@keel/api-client";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CreditMeter } from "./credit-meter";

const getCreditBalanceMock = vi.fn();

vi.mock("@/lib/billing/api", () => ({
  getCreditBalance: (orgSlug: string) => getCreditBalanceMock(orgSlug),
}));

function creditsOff() {
  vi.stubEnv("NEXT_PUBLIC_BILLING_CREDITS", "false");
}

function creditsOn() {
  vi.stubEnv("NEXT_PUBLIC_BILLING_CREDITS", "true");
}

beforeEach(() => {
  getCreditBalanceMock.mockReset();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("<CreditMeter> with credits disabled", () => {
  it("renders nothing and never calls the API", async () => {
    creditsOff();

    const { container } = render(<CreditMeter orgSlug="acme" />);

    // phase-4.md A.5: with the flag off there is "no meter" *and* no cost —
    // an empty DOM is only half of that; the request must not happen either.
    expect(container).toBeEmptyDOMElement();
    await Promise.resolve();
    expect(getCreditBalanceMock).not.toHaveBeenCalled();
  });
});

describe("<CreditMeter> with credits enabled", () => {
  it("renders the balance", async () => {
    creditsOn();
    getCreditBalanceMock.mockResolvedValue({ balance: 250 });

    render(<CreditMeter orgSlug="acme" />);

    expect(await screen.findByText("Credits: 250")).toBeInTheDocument();
    expect(getCreditBalanceMock).toHaveBeenCalledWith("acme");
  });

  it("renders nothing, and does not retry, when the server says credits are off", async () => {
    creditsOn();
    getCreditBalanceMock.mockRejectedValue(
      new NotFoundError({ code: "not_found", message: "Not found." }),
    );

    const { container } = render(<CreditMeter orgSlug="acme" />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
    // A 404 is "this feature does not exist" (billing/views.py
    // CreditBalanceView), not a transient failure — one request, no loop.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(getCreditBalanceMock).toHaveBeenCalledTimes(1);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the balance cannot be read at all", async () => {
    creditsOn();
    getCreditBalanceMock.mockRejectedValue(new Error("network down"));

    const { container } = render(<CreditMeter orgSlug="acme" />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("states the pre-flight cost against the balance in estimate mode", async () => {
    creditsOn();
    getCreditBalanceMock.mockResolvedValue({ balance: 250 });

    render(<CreditMeter orgSlug="acme" estimate={120} />);

    expect(await screen.findByText("This will use 120 of your 250 credits")).toBeInTheDocument();
  });

  it("warns when the estimate exceeds the balance", async () => {
    creditsOn();
    getCreditBalanceMock.mockResolvedValue({ balance: 50 });

    render(<CreditMeter orgSlug="acme" estimate={120} />);

    expect(
      await screen.findByText("This will use 120 of your 50 credits — not enough credits"),
    ).toBeInTheDocument();
  });

  it("hands the loaded state to a render prop for a future confirm dialog", async () => {
    creditsOn();
    getCreditBalanceMock.mockResolvedValue({ balance: 50 });

    render(
      <CreditMeter orgSlug="acme" estimate={120}>
        {(state) => (
          <button type="button" disabled={state.insufficient}>
            Run job
          </button>
        )}
      </CreditMeter>,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: "Run job" })).toBeDisabled());
  });

  it("never reports insufficient before the balance is known", () => {
    creditsOn();
    getCreditBalanceMock.mockReturnValue(new Promise(() => {}));

    render(
      <CreditMeter orgSlug="acme" estimate={120}>
        {(state) => <span>{state.insufficient ? "insufficient" : "unknown"}</span>}
      </CreditMeter>,
    );

    expect(screen.getByText("unknown")).toBeInTheDocument();
  });
});
