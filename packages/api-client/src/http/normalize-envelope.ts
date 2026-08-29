import type { ApiErrorEnvelope } from "./errors";

/** allauth flow ids that mean "not done yet", not "authentication failed". */
export const PENDING_FLOW_MESSAGES: Record<string, string> = {
  verify_email: "Check your email to verify your address before continuing.",
  mfa_authenticate: "Enter your authenticator code to finish signing in.",
};

/**
 * Three error shapes reach the client:
 *  - Keel's own envelope: { error: { code, message, details } }
 *  - allauth headless's field-error envelope: { status, errors: [{ code, param, message }] }
 *  - allauth headless's pending-flow envelope: { status: 401, data: { flows: [{ id, is_pending }] } } —
 *    a 401 carrying a pending email-verification flow, as signup emits. This is
 *    not an authentication failure; it becomes an UnauthorizedError whose
 *    `code` is the pending flow's id (e.g. "verify_email"), so callers can
 *    branch on `error.code` instead of re-parsing the response body.
 *
 * Normalize all three to ApiErrorEnvelope so one set of typed errors covers
 * every shape without callers knowing which API answered.
 */
export function normalizeErrorEnvelope(status: number, body: unknown): ApiErrorEnvelope {
  if (isKeelEnvelope(body)) {
    return body.error;
  }

  if (isAllauthPendingFlowEnvelope(body)) {
    const pendingFlow = body.data.flows.find((flow) => flow.is_pending);
    if (pendingFlow) {
      return {
        code: pendingFlow.id,
        message: PENDING_FLOW_MESSAGES[pendingFlow.id] ?? "Additional action required to continue.",
      };
    }
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

interface AllauthFlow {
  id: string;
  is_pending?: boolean;
}

function isAllauthPendingFlowEnvelope(body: unknown): body is { data: { flows: AllauthFlow[] } } {
  if (typeof body !== "object" || body === null || !("data" in body)) {
    return false;
  }

  const data = (body as { data: unknown }).data;
  return (
    typeof data === "object" &&
    data !== null &&
    "flows" in data &&
    Array.isArray((data as { flows: unknown }).flows)
  );
}
