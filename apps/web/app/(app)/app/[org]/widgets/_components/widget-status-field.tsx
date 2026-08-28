"use client";

import { WIDGET_STATUSES, widgetStatusLabel } from "@/lib/widgets/status";
import { Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@keel/ui";
import { AlertCircle } from "lucide-react";
import { Controller, type Control, type FieldError } from "react-hook-form";

/**
 * Status is an enum in practice (finding 11) — a `<Select>` here, paired
 * with `<Badge>` in the widgets table. `@keel/ui`'s `<FormField>` only
 * wraps a native `<input>`, so this composes the same label/error chrome
 * around a Radix `<Select>` via `Controller`.
 */
export function WidgetStatusField({
  control,
  error,
}: {
  control: Control<{ name: string; description?: string; status?: string }>;
  error?: FieldError;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="status">Status</Label>
      <Controller
        control={control}
        name="status"
        render={({ field }) => (
          <Select value={field.value || undefined} onValueChange={field.onChange}>
            <SelectTrigger id="status" aria-invalid={Boolean(error)} className="w-full">
              {/* Radix only learns an item's label once that item has
               * mounted — which happens on first open — so a value set
               * from async-loaded data (the edit form) would otherwise
               * show the placeholder until the user opens the dropdown.
               * Render the label explicitly instead of relying on that. */}
              <SelectValue placeholder="Select a status">
                {field.value ? widgetStatusLabel(field.value) : undefined}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {WIDGET_STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {widgetStatusLabel(status)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />
      {error ? (
        <p role="alert" className="flex items-center gap-1 text-sm text-destructive">
          <AlertCircle className="size-3.5 shrink-0" />
          {error.message}
        </p>
      ) : null}
    </div>
  );
}
