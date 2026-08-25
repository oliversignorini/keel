import { ApiError } from "@keel/api-client";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

/**
 * Maps a caught request error onto a react-hook-form form: a detail with a
 * `field` becomes a field-level error via `setError`; a detail with no
 * field, or an envelope with no details at all, is returned as a non-field
 * message for the caller to render (e.g. above the submit button).
 *
 * Returns null when `error` isn't an ApiError — the caller decides how to
 * handle unexpected errors (network failure, a 5xx) itself.
 */
export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
): string | null {
  if (!(error instanceof ApiError)) {
    return null;
  }

  if (error.details.length === 0) {
    return error.message;
  }

  let nonFieldMessage: string | null = null;

  for (const detail of error.details) {
    if (detail.field) {
      setError(detail.field as Path<T>, { type: "server", message: detail.message });
    } else {
      nonFieldMessage = detail.message;
    }
  }

  return nonFieldMessage;
}
