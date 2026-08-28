/**
 * Widget `status` is a free-text field on the API (docs/adr allow any
 * string), but in practice takes one of three values — model the common
 * case in the UI (a `<Select>` in forms, a `<Badge>` in the table) while
 * still rendering an unrecognised value instead of dropping it.
 */
export const WIDGET_STATUSES = ["draft", "active", "paused"] as const;
export type WidgetStatus = (typeof WIDGET_STATUSES)[number];

const WIDGET_STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  active: "Active",
  paused: "Paused",
};

export type WidgetStatusBadgeVariant =
  | "default"
  | "secondary"
  | "destructive"
  | "outline"
  | "success"
  | "warning";

const WIDGET_STATUS_BADGE_VARIANTS: Record<string, WidgetStatusBadgeVariant> = {
  draft: "outline",
  active: "success",
  paused: "warning",
};

export function widgetStatusLabel(status: string): string {
  if (!status) return "—";
  return WIDGET_STATUS_LABELS[status] ?? status.charAt(0).toUpperCase() + status.slice(1);
}

export function widgetStatusBadgeVariant(status: string): WidgetStatusBadgeVariant {
  return WIDGET_STATUS_BADGE_VARIANTS[status] ?? "secondary";
}
