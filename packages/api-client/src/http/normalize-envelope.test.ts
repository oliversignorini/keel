import { describe, expect, it } from "vitest";

import { normalizeErrorEnvelope } from "./normalize-envelope";

describe("normalizeErrorEnvelope", () => {
  it("passes a Keel envelope through unchanged", () => {
    const body = {
      error: {
        code: "SEAT_LIMIT_EXCEEDED",
        message: "This plan includes 10 seats. Upgrade to add more.",
        details: [{ field: "email", message: "Already a member." }],
      },
    };

    expect(normalizeErrorEnvelope(402, body)).toEqual(body.error);
  });

  it("adapts an allauth errors[] envelope, mapping param to field", () => {
    const body = {
      status: 400,
      errors: [{ code: "email_taken", param: "email", message: "A user is already registered with this email." }],
    };

    expect(normalizeErrorEnvelope(400, body)).toEqual({
      code: "email_taken",
      message: "A user is already registered with this email.",
      details: [{ field: "email", message: "A user is already registered with this email." }],
    });
  });

  it("collects every allauth field error into details", () => {
    const body = {
      status: 400,
      errors: [
        { code: "required", param: "email", message: "This field is required." },
        { code: "required", param: "password", message: "This field is required." },
      ],
    };

    expect(normalizeErrorEnvelope(400, body).details).toHaveLength(2);
  });

  it("maps allauth's pending-flow envelope to a code matching the flow id", () => {
    const body = {
      status: 401,
      data: { flows: [{ id: "verify_email", is_pending: true }] },
    };

    expect(normalizeErrorEnvelope(401, body)).toEqual({
      code: "verify_email",
      message: "Check your email to verify your address before continuing.",
    });
  });

  it("picks the pending flow when several flows are listed", () => {
    const body = {
      status: 401,
      data: {
        flows: [
          { id: "login", is_pending: false },
          { id: "mfa_authenticate", is_pending: true },
        ],
      },
    };

    expect(normalizeErrorEnvelope(401, body).code).toBe("mfa_authenticate");
  });

  it("falls back to a generic envelope for an unrecognized body", () => {
    expect(normalizeErrorEnvelope(500, { unexpected: true })).toEqual({
      code: "unknown_error",
      message: "Request failed with status 500.",
    });
  });

  it("falls back to a generic envelope when the body is not JSON", () => {
    expect(normalizeErrorEnvelope(500, undefined)).toEqual({
      code: "unknown_error",
      message: "Request failed with status 500.",
    });
  });
});
