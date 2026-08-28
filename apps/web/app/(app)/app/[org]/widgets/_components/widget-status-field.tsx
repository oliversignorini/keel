"use client";

import { Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@keel/ui";
import { AlertCircle } from "lucide-react";
import { Controller, type Control, type FieldError } from "react-hook-form";

export const STATUS_OPTIONS = ["draft", "active", "paused"] as const;

export function statusLabel(value: string): string {
  if (!value) return "—";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** `<WidgetStatusField>` — `@keel/ui`'s `<FormField>` only wraps a native
 * `<input>`, so this composes the same label/error chrome around a Radix
 * `<Select>` via `Controller`. */
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
                {field.value ? statusLabel(field.value) : undefined}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {statusLabel(option)}
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
