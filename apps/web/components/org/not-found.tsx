import type { ReactNode } from "react";
import { SearchX } from "lucide-react";

import { Card, CardContent } from "@keel/ui";

/**
 * One shared "not found" panel (finding 36) — used wherever a resource
 * can't be resolved for the current viewer (wrong org, wrong widget,
 * wrong anything) instead of each call site hand-rolling its own layout.
 * Deliberately says "doesn't exist, or you're not allowed to see it"
 * rather than distinguishing the two — see `[org]/layout.tsx`'s
 * docstring on why existence isn't disclosed across tenant boundaries.
 */
export function NotFound({
  title,
  description = "It doesn't exist, or you don't have access to it.",
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
        <SearchX className="size-8 text-muted-foreground" />
        <div className="flex flex-col gap-1">
          <h1 className="text-lg font-semibold text-foreground">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        {action}
      </CardContent>
    </Card>
  );
}
