"use client";

import { Can } from "@/components/org/can";
import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { useOrgContext } from "@/lib/org/org-context";
import { Perm } from "@/lib/org/permissions";
import { deleteWidget, getWidget, updateWidget } from "@/lib/widgets/api";
import { zodResolver } from "@hookform/resolvers/zod";
import type { Widget } from "@keel/api-client";
import { FormField, PageHeader, ResourceForm } from "@keel/ui";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const widgetFormSchema = z.object({
  name: z.string().min(1, "Name is required.").max(255),
  description: z.string().max(2000).optional(),
  status: z.string().max(32).optional(),
});
type WidgetFormValues = z.infer<typeof widgetFormSchema>;

/** `/[org]/widgets/[id]` — the update/delete half of the Widget vertical
 * slice (docs/plans/phase-6.md 6.D). */
export default function WidgetDetailPage() {
  const router = useRouter();
  const params = useParams<{ org: string; id: string }>();
  const { currentOrg } = useOrgContext();
  const [widget, setWidget] = useState<Widget | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<WidgetFormValues>({
    resolver: zodResolver(widgetFormSchema),
    values: widget
      ? { name: widget.name, description: widget.description ?? "", status: widget.status ?? "" }
      : undefined,
  });

  useEffect(() => {
    if (!currentOrg) return;
    let cancelled = false;
    getWidget(currentOrg.slug, params.id)
      .then((result) => {
        if (!cancelled) setWidget(result);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      });
    return () => {
      cancelled = true;
    };
  }, [currentOrg, params.id]);

  if (!currentOrg) return null;

  if (notFound) {
    return (
      <div className="rounded-lg border border-border p-6">
        <h1 className="mb-2 text-lg font-semibold text-foreground">Widget not found</h1>
        <p className="text-sm text-muted-foreground">
          It doesn&apos;t exist, or it belongs to a different organisation.
        </p>
      </div>
    );
  }

  if (!widget) return null;

  async function onSubmit(values: WidgetFormValues) {
    setFormError(null);
    try {
      const updated = await updateWidget(currentOrg!.slug, params.id, values);
      setWidget(updated);
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  async function onDelete() {
    if (!window.confirm(`Delete ${widget!.name}? This cannot be undone.`)) return;
    await deleteWidget(currentOrg!.slug, params.id);
    router.push(`/${currentOrg!.slug}/widgets`);
  }

  return (
    <div className="max-w-lg">
      <PageHeader
        title={widget.name}
        actions={
          <Can code={Perm.WIDGETS_MANAGE}>
            <button
              type="button"
              onClick={() => void onDelete()}
              className="rounded-md border border-destructive px-3 py-2 text-sm font-medium text-destructive"
            >
              Delete
            </button>
          </Can>
        }
      />
      <ResourceForm
        onSubmit={handleSubmit(onSubmit)}
        formError={formError}
        submitLabel="Save changes"
        submittingLabel="Saving…"
        isSubmitting={isSubmitting}
      >
        <FormField label="Name" id="name" error={errors.name?.message} {...register("name")} />
        <FormField
          label="Status"
          id="status"
          error={errors.status?.message}
          {...register("status")}
        />
        <FormField
          label="Description"
          id="description"
          error={errors.description?.message}
          {...register("description")}
        />
      </ResourceForm>
    </div>
  );
}
