import type { FormHTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";

/** `<ResourceForm>` — the CRUD-form chrome every generated resource form
 * shares (PRD §5 component inventory; docs/plans/phase-6.md 6.C): a
 * top-level error banner (for a 400 field error the caller's `setError`
 * couldn't map to a specific field — see
 * apps/web/lib/api/form-error-mapper.ts), the fields themselves (the
 * caller wires react-hook-form to whatever inputs it passes as
 * children), and a Cancel/Submit footer. Purely presentational — the
 * caller owns `useForm`, validation, and the submit handler. */
export function ResourceForm({
  onSubmit,
  formError,
  submitLabel,
  submittingLabel,
  isSubmitting,
  onCancel,
  children,
  ...formProps
}: {
  onSubmit: FormHTMLAttributes<HTMLFormElement>["onSubmit"];
  formError?: string | null;
  submitLabel: string;
  submittingLabel?: string;
  isSubmitting?: boolean;
  onCancel?: () => void;
  children: ReactNode;
} & Omit<FormHTMLAttributes<HTMLFormElement>, "onSubmit">) {
  return (
    <form onSubmit={onSubmit} noValidate {...formProps} className={cn("flex flex-col gap-4")}>
      {formError ? (
        <p role="alert" className="text-sm text-destructive">
          {formError}
        </p>
      ) : null}
      {children}
      <div className="flex items-center justify-end gap-2 pt-2">
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md px-3 py-2 text-sm font-medium text-foreground hover:bg-accent"
          >
            Cancel
          </button>
        ) : null}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {isSubmitting ? (submittingLabel ?? submitLabel) : submitLabel}
        </button>
      </div>
    </form>
  );
}
