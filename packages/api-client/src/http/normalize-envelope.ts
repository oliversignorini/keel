import type { ApiErrorEnvelope } from "./errors";

/**
 * Two error shapes reach the client during Phase 2:
 *  - Keel's own envelope (keel-prd.md §7): { error: { code, message, details } }
 *  - allauth headless's envelope: { status, errors: [{ code, param, message }] }
 *
 * Normalize both to ApiErrorEnvelope so one set of typed errors covers both
 * without callers knowing which API answered.
 */
export function normalizeErrorEnvelope(status: number, body: unknown): ApiErrorEnvelope {
  if (isKeelEnvelope(body)) {
    return body.error;
  }

  if (isAllauthEnvelope(body)) {
    const [first] = body.errors;
    return {
      code: first?.code ?? "unknown_error",
      message: first?.message ?? "Request failed.",
      details: body.errors.map((error) => ({
        field: error.param,
        message: error.message,
      })),
    };
  }

  return {
    code: "unknown_error",
    message: `Request failed with status ${status}.`,
  };
}

function isKeelEnvelope(body: unknown): body is { error: ApiErrorEnvelope } {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as { error: unknown }).error === "object" &&
    (body as { error: unknown }).error !== null
  );
}

interface AllauthFieldError {
  code?: string;
  param?: string;
  message: string;
}

function isAllauthEnvelope(body: unknown): body is { status: number; errors: AllauthFieldError[] } {
  return (
    typeof body === "object" &&
    body !== null &&
    "errors" in body &&
    Array.isArray((body as { errors: unknown }).errors)
  );
}
