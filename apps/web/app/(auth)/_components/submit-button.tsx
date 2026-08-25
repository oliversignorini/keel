import { cn } from "@/lib/cn";
import type { ButtonHTMLAttributes } from "react";

export function SubmitButton({
  className,
  children,
  ...buttonProps
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="submit"
      className={cn(
        "rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900",
        className,
      )}
      {...buttonProps}
    >
      {children}
    </button>
  );
}
