/**
 * Typed errors for the Keel error envelope:
 *   { "error": { "code": "...", "message": "...", "details": [{ field, message }] } }
 *
 * `details` is always this one shape — list[{field, message}] | null — even
 * for a 403: structured denial context (which permission was required, which
 * invariant blocked the action) rides in a sibling `denial` key instead of
 * overloading `details` with a second shape.
 * `ForbiddenError` is where `denial` actually appears; every other error
 * class exposes it too for uniformity, always empty there.
 *
 * allauth's own headless endpoints (called directly by the auth flows) reply with a
 * different shape — { status, errors: [{ code, param, message }] } — so
 * normalizeErrorEnvelope() (./normalize-envelope.ts) adapts both into this
 * one envelope before an error class is chosen. One status maps to exactly
 * one class; callers narrow with `instanceof` instead of switching on
 * `.status`.
 */

export interface ApiErrorDetail {
  field?: string;
  message: string;
}

export interface ApiErrorEnvelope {
  code: string;
  message: string;
  details?: ApiErrorDetail[];
  /** Structured 403 denial context — e.g.
   * `{ required: "members.remove" }` or `{ membership_id: "..." }`. The
   * permission code required (or the reason code itself) is enumerable
   * via `GET /api/v1/permissions/`'s `denial_reasons`. */
  denial?: Record<string, unknown> | null;
}

export abstract class ApiError extends Error {
  abstract readonly status: number;
  readonly code: string;
  readonly details: ApiErrorDetail[];
  readonly denial: Record<string, unknown> | null;

  constructor(envelope: ApiErrorEnvelope) {
    super(envelope.message);
    this.code = envelope.code;
    this.details = envelope.details ?? [];
    this.denial = envelope.denial ?? null;
  }
}

export class BadRequestError extends ApiError {
  readonly status = 400 as const;
}

export class UnauthorizedError extends ApiError {
  readonly status = 401 as const;
}

export class PaymentRequiredError extends ApiError {
  readonly status = 402 as const;
}

export class ForbiddenError extends ApiError {
  readonly status = 403 as const;
}

export class NotFoundError extends ApiError {
  readonly status = 404 as const;
}

export class ConflictError extends ApiError {
  readonly status = 409 as const;
}

export class UnprocessableEntityError extends ApiError {
  readonly status = 422 as const;
}

export class RateLimitedError extends ApiError {
  readonly status = 429 as const;
  readonly retryAfterSeconds: number | undefined;

  constructor(envelope: ApiErrorEnvelope, retryAfterSeconds: number | undefined) {
    super(envelope);
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export class UnknownApiError extends ApiError {
  readonly status: number;

  constructor(status: number, envelope: ApiErrorEnvelope) {
    super(envelope);
    this.status = status;
  }
}

export function errorFromStatus(
  status: number,
  envelope: ApiErrorEnvelope,
  retryAfterSeconds?: number,
): ApiError {
  switch (status) {
    case 400:
      return new BadRequestError(envelope);
    case 401:
      return new UnauthorizedError(envelope);
    case 402:
      return new PaymentRequiredError(envelope);
    case 403:
      return new ForbiddenError(envelope);
    case 404:
      return new NotFoundError(envelope);
    case 409:
      return new ConflictError(envelope);
    case 422:
      return new UnprocessableEntityError(envelope);
    case 429:
      return new RateLimitedError(envelope, retryAfterSeconds);
    default:
      return new UnknownApiError(status, envelope);
  }
}
