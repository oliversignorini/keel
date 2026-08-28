import type { ReactNode } from "react";

import { Separator } from "./components/ui/separator";

/** `<PageHeader>` — title, optional description, optional actions on the
 * right, optional breadcrumb above the title (PRD §5 component
 * inventory; finding 22). */
export function PageHeader({
  breadcrumb,
  title,
  description,
  actions,
}: {
  breadcrumb?: ReactNode;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4">
      {breadcrumb ? <div>{breadcrumb}</div> : null}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      <Separator />
    </div>
  );
}
