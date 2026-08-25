import type { ReactNode } from "react";

/** `<EmptyState>` — every empty state offers a primary action
 * (docs/plans/phase-6.md 6.C, acceptance). */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border px-6 py-16 text-center">
      <h2 className="text-sm font-medium text-foreground">{title}</h2>
      {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {action}
    </div>
  );
}
