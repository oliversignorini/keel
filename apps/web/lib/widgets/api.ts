/**
 * Thin, typed wrappers around the generated Widget client
 * (@keel/api-client — see packages/api-client/orval.config.ts), same
 * shape as lib/org/api.ts: nothing here reimplements transport, auth, or
 * error handling.
 */
import {
  unwrapData,
  createWidget as generatedCreateWidget,
  deleteWidget as generatedDeleteWidget,
  listWidgets as generatedListWidgets,
  retrieveWidget,
  updateWidget as generatedUpdateWidget,
  type PageWidgetOut,
  type WidgetOut,
} from "@keel/api-client";

export interface WidgetWriteBody {
  name: string;
  description?: string;
  status?: string;
}

export async function listWidgets(
  orgSlug: string,
  params?: { cursor?: string; limit?: number },
): Promise<PageWidgetOut> {
  const result = await generatedListWidgets(orgSlug, params);
  return unwrapData(result);
}

export async function getWidget(orgSlug: string, id: string): Promise<WidgetOut> {
  const result = await retrieveWidget(orgSlug, id);
  return unwrapData(result);
}

export async function createWidget(orgSlug: string, body: WidgetWriteBody): Promise<WidgetOut> {
  const result = await generatedCreateWidget(orgSlug, body as never);
  return unwrapData(result);
}

export async function updateWidget(
  orgSlug: string,
  id: string,
  body: Partial<WidgetWriteBody>,
): Promise<WidgetOut> {
  const result = await generatedUpdateWidget(orgSlug, id, body as never);
  return unwrapData(result);
}

export async function deleteWidget(orgSlug: string, id: string): Promise<void> {
  await generatedDeleteWidget(orgSlug, id);
}
