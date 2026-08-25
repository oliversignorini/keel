import { type InputHTMLAttributes, type TextareaHTMLAttributes, forwardRef } from "react";

import { cn } from "./cn";

interface FieldChromeProps {
  label: string;
  id: string;
  error?: string;
}

function FieldChrome({
  label,
  id,
  error,
  children,
}: FieldChromeProps & { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

type FormFieldProps = FieldChromeProps & InputHTMLAttributes<HTMLInputElement>;

/** A labeled input with an inline error slot — the shape
 * `<ResourceForm>` fields are built from (PRD §5 component inventory). */
export const FormField = forwardRef<HTMLInputElement, FormFieldProps>(function FormField(
  { label, id, error, className, ...inputProps },
  ref,
) {
  return (
    <FieldChrome label={label} id={id} error={error}>
      <input
        id={id}
        ref={ref}
        aria-invalid={Boolean(error)}
        className={cn(
          "rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring",
          className,
        )}
        {...inputProps}
      />
    </FieldChrome>
  );
});

type FormTextareaProps = FieldChromeProps & TextareaHTMLAttributes<HTMLTextAreaElement>;

export const FormTextarea = forwardRef<HTMLTextAreaElement, FormTextareaProps>(
  function FormTextarea({ label, id, error, className, ...textareaProps }, ref) {
    return (
      <FieldChrome label={label} id={id} error={error}>
        <textarea
          id={id}
          ref={ref}
          aria-invalid={Boolean(error)}
          className={cn(
            "rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring",
            className,
          )}
          {...textareaProps}
        />
      </FieldChrome>
    );
  },
);
