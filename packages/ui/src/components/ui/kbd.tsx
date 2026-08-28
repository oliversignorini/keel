import type { ComponentProps } from "react";

import { cn } from "../../cn";

/** Local primitive — shadcn ships no `kbd` component. Renders a keyboard
 * shortcut hint, e.g. inside the ⌘K trigger button. */
export function Kbd({ className, ...props }: ComponentProps<"kbd">) {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border border-border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}
