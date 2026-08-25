import { BadRequestError, UnprocessableEntityError } from "@keel/api-client";
import { describe, expect, it, vi } from "vitest";

import { applyFieldErrors } from "./form-error-mapper";

describe("applyFieldErrors", () => {
  it("sets a field error for each detail that names a field", () => {
    const setError = vi.fn();
    const error = new UnprocessableEntityError({
      code: "validation_error",
      message: "Fix the highlighted fields.",
      details: [
        { field: "email", message: "Already a member." },
        { field: "password", message: "Too short." },
      ],
    });

    applyFieldErrors(error, setError);

    expect(setError).toHaveBeenCalledWith("email", { type: "server", message: "Already a member." });
    expect(setError).toHaveBeenCalledWith("password", { type: "server", message: "Too short." });
    expect(setError).toHaveBeenCalledTimes(2);
  });

  it("returns a non-field message for a detail with no field", () => {
    const setError = vi.fn();
    const error = new BadRequestError({
      code: "invalid_credentials",
      message: "Unable to sign in.",
      details: [{ message: "Email or password is incorrect." }],
    });

    const nonFieldMessage = applyFieldErrors(error, setError);

    expect(nonFieldMessage).toBe("Email or password is incorrect.");
    expect(setError).not.toHaveBeenCalled();
  });

  it("falls back to the envelope message when there are no details", () => {
    const setError = vi.fn();
    const error = new BadRequestError({ code: "bad_request", message: "Something went wrong." });

    expect(applyFieldErrors(error, setError)).toBe("Something went wrong.");
    expect(setError).not.toHaveBeenCalled();
  });

  it("returns null and sets nothing for a non-ApiError", () => {
    const setError = vi.fn();

    expect(applyFieldErrors(new Error("network down"), setError)).toBeNull();
    expect(setError).not.toHaveBeenCalled();
  });
});
