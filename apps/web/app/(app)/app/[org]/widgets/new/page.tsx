"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { useOrgContext } from "@/lib/org/org-context";
import { createWidget } from "@/lib/widgets/api";
import { zodResolver } from "@hookform/resolvers/zod";
import { FormField, PageHeader, ResourceForm } from "@keel/ui";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const widgetFormSchema = z.object({
  name: z.string().min(1, "Name is required.").max(255),
  description: z.string().max(2000).optional(),
  status: z.string().max(32).optional(),
});
type WidgetFormValues = z.infer<typeof widgetFormSchema>;

/** `/[org]/widgets/new` — the create half of the Widget vertical slice
 * (docs/plans/phase-6.md 6.D). */
export default function NewWidgetPage() {
  const router = useRouter();
  const { currentOrg } = useOrgContext();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<WidgetFormValues>({ resolver: zodResolver(widgetFormSchema) });

  if (!currentOrg) return null;

  async function onSubmit(values: WidgetFormValues) {
    setFormError(null);
    try {
      const widget = await createWidget(currentOrg!.slug, values);
      router.push(`/${currentOrg!.slug}/widgets/${widget.id}`);
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <div className="max-w-lg">
      <PageHeader title="New widget" />
      <ResourceForm
        onSubmit={handleSubmit(onSubmit)}
        formError={formError}
        submitLabel="Create widget"
        submittingLabel="Creating…"
        isSubmitting={isSubmitting}
        onCancel={() => router.push(`/${currentOrg!.slug}/widgets`)}
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
