import { cn } from "@/lib/cn";
import type { InputHTMLAttributes } from "react";

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

/** A labelled input with an associated, accessible error message. */
export function FormField({ label, error, id, className, ...inputProps }: FormFieldProps) {
  const errorId = error ? `${id}-error` : undefined;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        className={cn(
          "rounded-md border border-neutral-300 px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-neutral-900 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100 dark:focus-visible:ring-neutral-100",
          error && "border-red-500 focus-visible:ring-red-500",
          className,
        )}
        {...inputProps}
      />
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}
