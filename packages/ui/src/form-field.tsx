import { type InputHTMLAttributes, type TextareaHTMLAttributes, forwardRef } from "react";
import { AlertCircle } from "lucide-react";

import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { Textarea } from "./components/ui/textarea";

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
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p role="alert" className="flex items-center gap-1 text-sm text-destructive">
          <AlertCircle className="size-3.5 shrink-0" />
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
      <Input
        id={id}
        ref={ref}
        aria-invalid={Boolean(error)}
        className={className}
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
        <Textarea
          id={id}
          ref={ref}
          aria-invalid={Boolean(error)}
          className={className}
          {...textareaProps}
        />
      </FieldChrome>
    );
  },
);
