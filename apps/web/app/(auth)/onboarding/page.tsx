"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { toAppHost } from "@/lib/host";
import { createOrganization } from "@/lib/org/api";
import {
  Alert,
  AlertDescription,
  Button,
  Form,
  FormControl,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  RHFFormField,
} from "@keel/ui";
import { AlertCircle, Loader2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

interface OnboardingFormValues {
  name: string;
}

/**
 * `/onboarding` (PRD §5 Routes, §6 "Signup → first organisation"):
 * creates the visitor's first organisation. `createOrganization` calls
 * `POST /api/v1/orgs/`, which is atomic end to end on the server
 * — org, Owner membership, and the three preset roles are created
 * together or not at all (organizations/services.py `create_organization`,
 * phase-3.md acceptance: "Creating an organisation is atomic ... all or
 * nothing").
 */
export default function OnboardingPage() {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<OnboardingFormValues>({ defaultValues: { name: "" } });
  const { isSubmitting } = form.formState;

  async function onSubmit(values: OnboardingFormValues) {
    setFormError(null);
    try {
      const organization = await createOrganization({ name: values.name });
      window.location.href = `${window.location.protocol}//${toAppHost(window.location.host)}/${organization.slug}`;
    } catch (error) {
      setFormError(applyFieldErrors(error, form.setError));
    }
  }

  return (
    <>
      <h1 className="mb-2 text-lg font-semibold text-foreground">Create your organisation</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        You&apos;ll be the Owner, and can invite teammates once it&apos;s created.
      </p>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          {formError ? (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}
          <RHFFormField
            control={form.control}
            name="name"
            rules={{ required: "Organisation name is required." }}
            render={({ field }) => (
              <FormItem>
                <FormLabel>Organisation name</FormLabel>
                <FormControl>
                  <Input autoComplete="organization" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="animate-spin" /> : null}
            {isSubmitting ? "Creating…" : "Create organisation"}
          </Button>
        </form>
      </Form>
    </>
  );
}
