/**
 * Thin, typed wrappers around the generated Widget client
 * (@keel/api-client — see packages/api-client/orval.config.ts), same
 * shape as lib/org/api.ts: nothing here reimplements transport, auth, or
 * error handling.
 */
import {
  organizationsWidgetsCreate,
  organizationsWidgetsDestroy,
  organizationsWidgetsList,
  organizationsWidgetsPartialUpdate,
  organizationsWidgetsRetrieve,
  type PaginatedWidgetList,
  type Widget,
} from "@keel/api-client";

export interface WidgetWriteBody {
  name: string;
  description?: string;
  status?: string;
}

export async function listWidgets(
  orgSlug: string,
  params?: { cursor?: string; limit?: number },
): Promise<PaginatedWidgetList> {
  const result = await organizationsWidgetsList(orgSlug, params);
  return result.data;
}

export async function getWidget(orgSlug: string, id: string): Promise<Widget> {
  const result = await organizationsWidgetsRetrieve(orgSlug, id);
  return result.data;
}

export async function createWidget(orgSlug: string, body: WidgetWriteBody): Promise<Widget> {
  const result = await organizationsWidgetsCreate(orgSlug, body as never);
  return result.data;
}

export async function updateWidget(
  orgSlug: string,
  id: string,
  body: Partial<WidgetWriteBody>,
): Promise<Widget> {
  const result = await organizationsWidgetsPartialUpdate(orgSlug, id, body as never);
  return result.data;
}

export async function deleteWidget(orgSlug: string, id: string): Promise<void> {
  await organizationsWidgetsDestroy(orgSlug, id);
}
