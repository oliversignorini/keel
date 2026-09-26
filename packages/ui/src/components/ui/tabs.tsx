import type { ComponentProps } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Tabs as TabsPrimitive } from "radix-ui";

import { cn } from "../../cn";

const tabsVariants = cva("flex flex-col", {
  variants: {
    spacing: {
      default: "gap-2",
      relaxed: "gap-6",
    },
  },
  defaultVariants: {
    spacing: "default",
  },
});

export function Tabs({
  className,
  spacing,
  ...props
}: ComponentProps<typeof TabsPrimitive.Root> & VariantProps<typeof tabsVariants>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn(tabsVariants({ spacing }), className)}
      {...props}
    />
  );
}

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "inline-flex h-9 w-fit items-center justify-center rounded-lg bg-muted p-[3px] text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm dark:data-[state=active]:border-input dark:data-[state=active]:bg-input/30 dark:data-[state=active]:text-foreground",
        className,
      )}
      {...props}
    />
  );
}

const tabsContentVariants = cva("flex-1 outline-none", {
  variants: {
    focusable: {
      true: "focus-visible:rounded-md focus-visible:ring-[3px] focus-visible:ring-ring/50",
      false: "",
    },
  },
  defaultVariants: {
    focusable: true,
  },
});

export function TabsContent({
  className,
  focusable = true,
  ...props
}: ComponentProps<typeof TabsPrimitive.Content> & VariantProps<typeof tabsContentVariants>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      tabIndex={focusable ? undefined : -1}
      className={cn(tabsContentVariants({ focusable }), className)}
      {...props}
    />
  );
}
