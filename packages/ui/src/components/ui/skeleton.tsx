import type { ComponentProps } from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../../cn";

/** Sizeless by design: `<Skeleton>` fills whatever box its parent gives it
 * (`h-full w-full`). Put layout (`h-4 w-24`, …) on a wrapper element around
 * it instead of on the skeleton itself — its contract allows no classes.
 * `shape="pill"` is the one variant it owns, for a circular/pill-shaped
 * placeholder (an avatar, a badge). */
export const skeletonVariants = cva("block h-full w-full animate-pulse bg-accent", {
  variants: {
    shape: {
      default: "rounded-md",
      pill: "rounded-full",
    },
  },
  defaultVariants: {
    shape: "default",
  },
});

export function Skeleton({
  className,
  shape,
  ...props
}: ComponentProps<"div"> & VariantProps<typeof skeletonVariants>) {
  return (
    <div data-slot="skeleton" className={cn(skeletonVariants({ shape }), className)} {...props} />
  );
}
