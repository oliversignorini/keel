import { UnauthorizedError } from "@keel/api-client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const identityFetch = vi.fn();
const authReauthenticate = vi.fn();

vi.mock("@keel/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@keel/api-client")>()),
  identityFetch: (...args: unknown[]) => identityFetch(...args),
  authReauthenticate: (...args: unknown[]) => authReauthenticate(...args),
}));

import { TotpSection } from "./totp-section";

const reauthRequired = () =>
  new UnauthorizedError({ code: "unauthorized", message: "Reauthentication required" });

async function openInactive() {
  identityFetch.mockResolvedValueOnce({ data: { data: { provisioning_uri: "otpauth://x" } } });
  render(<TotpSection />);
  await screen.findByText("otpauth://x");
  fireEvent.change(screen.getByLabelText("Code"), { target: { value: "123456" } });
}

describe("TotpSection reauthentication (allauth >= 65.20)", () => {
  beforeEach(() => {
    identityFetch.mockReset();
    authReauthenticate.mockReset();
  });

  it("asks for the password on 401, reauthenticates, then retries activation", async () => {
    await openInactive();
    identityFetch.mockRejectedValueOnce(reauthRequired());
    fireEvent.click(screen.getByRole("button", { name: "Enable" }));

    const password = await screen.findByLabelText("Password");
    fireEvent.change(password, { target: { value: "s3cret-pass-1" } });
    authReauthenticate.mockResolvedValueOnce({});
    identityFetch.mockResolvedValueOnce({});
    fireEvent.click(screen.getByRole("button", { name: "Confirm password" }));

    await screen.findByText("Two-factor authentication is enabled.");
    expect(authReauthenticate).toHaveBeenCalledWith({ password: "s3cret-pass-1" });
    const activations = identityFetch.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(activations).toHaveLength(2);
  });

  it("keeps the prompt and shows the error when the password is wrong", async () => {
    await openInactive();
    identityFetch.mockRejectedValueOnce(reauthRequired());
    fireEvent.click(screen.getByRole("button", { name: "Enable" }));
    fireEvent.change(await screen.findByLabelText("Password"), { target: { value: "nope" } });
    authReauthenticate.mockRejectedValueOnce(
      new UnauthorizedError({
        code: "unauthorized",
        message: "The password you entered is incorrect.",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm password" }));

    await waitFor(() =>
      expect(screen.getByText("The password you entered is incorrect.")).toBeTruthy(),
    );
    expect(screen.getByLabelText("Password")).toBeTruthy();
  });
});
