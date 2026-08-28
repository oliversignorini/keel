import type { FormHTMLAttributes, ReactNode } from "react";
import { AlertCircle, Loader2 } from "lucide-react";

import { Alert, AlertDescription } from "./components/ui/alert";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardFooter } from "./components/ui/card";
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
    <form onSubmit={onSubmit} noValidate {...formProps} className={cn("contents")}>
      <Card>
        <CardContent className="flex flex-col gap-4">
          {formError ? (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}
          {children}
        </CardContent>
        <CardFooter className="justify-end gap-2">
          {onCancel ? (
            <Button type="button" variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          ) : null}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="animate-spin" /> : null}
            {isSubmitting ? (submittingLabel ?? submitLabel) : submitLabel}
          </Button>
        </CardFooter>
      </Card>
    </form>
  );
}
