import { describe, expect, it } from "vitest";

import {
  BadRequestError,
  ConflictError,
  ForbiddenError,
  NotFoundError,
  PaymentRequiredError,
  RateLimitedError,
  UnauthorizedError,
  UnknownApiError,
  UnprocessableEntityError,
  errorFromStatus,
} from "./errors";

const envelope = { code: "SEAT_LIMIT_EXCEEDED", message: "Upgrade to add more.", details: [] };

describe("errorFromStatus", () => {
  it.each([
    [400, BadRequestError],
    [401, UnauthorizedError],
    [402, PaymentRequiredError],
    [403, ForbiddenError],
    [404, NotFoundError],
    [409, ConflictError],
    [422, UnprocessableEntityError],
  ])("maps status %d to %s", (status, ErrorClass) => {
    const error = errorFromStatus(status, envelope);
    expect(error).toBeInstanceOf(ErrorClass);
    expect(error.status).toBe(status);
    expect(error.code).toBe("SEAT_LIMIT_EXCEEDED");
    expect(error.message).toBe("Upgrade to add more.");
  });

  it("maps 429 to RateLimitedError and carries Retry-After", () => {
    const error = errorFromStatus(429, envelope, 30);
    expect(error).toBeInstanceOf(RateLimitedError);
    expect((error as RateLimitedError).retryAfterSeconds).toBe(30);
  });

  it("falls back to UnknownApiError for an unmapped status", () => {
    const error = errorFromStatus(500, envelope);
    expect(error).toBeInstanceOf(UnknownApiError);
    expect(error.status).toBe(500);
  });

  it("carries field-level details through", () => {
    const error = errorFromStatus(422, {
      code: "validation_error",
      message: "Fix the highlighted fields.",
      details: [{ field: "email", message: "Already a member." }],
    });
    expect(error.details).toEqual([{ field: "email", message: "Already a member." }]);
  });
});
