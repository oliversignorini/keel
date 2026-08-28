/**
 * Thin, typed wrappers around the generated __Resource__ client
 * (@keel/api-client — see packages/api-client/orval.config.ts), same
 * shape as lib/org/api.ts: nothing here reimplements transport, auth, or
 * error handling.
 */
import {
  unwrapData,
  create__Resource__ as generatedCreate__Resource__,
  delete__Resource__ as generatedDelete__Resource__,
  list__Resources__ as generatedList__Resources__,
  retrieve__Resource__,
  update__Resource__ as generatedUpdate__Resource__,
  type Page__Resource__Out,
  type __Resource__Out,
} from "@keel/api-client";

// keel:if has_fields
export interface __Resource__WriteBody {
  // keel:insert write_body_fields
}
// keel:endif
// keel:if no_fields
export type __Resource__WriteBody = Record<string, never>;
// keel:endif

export async function list__Resources__(
  orgSlug: string,
  params?: { cursor?: string; limit?: number },
): Promise<Page__Resource__Out> {
  const result = await generatedList__Resources__(orgSlug, params);
  return unwrapData(result);
}

export async function get__Resource__(orgSlug: string, id: string): Promise<__Resource__Out> {
  const result = await retrieve__Resource__(orgSlug, id);
  return unwrapData(result);
}

export async function create__Resource__(
  orgSlug: string,
  body: __Resource__WriteBody,
): Promise<__Resource__Out> {
  const result = await generatedCreate__Resource__(orgSlug, body as never);
  return unwrapData(result);
}

export async function update__Resource__(
  orgSlug: string,
  id: string,
  body: Partial<__Resource__WriteBody>,
): Promise<__Resource__Out> {
  const result = await generatedUpdate__Resource__(orgSlug, id, body as never);
  return unwrapData(result);
}

export async function delete__Resource__(orgSlug: string, id: string): Promise<void> {
  await generatedDelete__Resource__(orgSlug, id);
}
