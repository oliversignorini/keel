"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { toAppHost } from "@/lib/host";
import { createOrganization } from "@/lib/org/api";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { FormError } from "../_components/form-error";
import { FormField } from "../_components/form-field";
import { SubmitButton } from "../_components/submit-button";

interface OnboardingFormValues {
  name: string;
}

/**
 * `/onboarding` (PRD §5 Routes, §6 "Signup → first organisation"):
 * creates the visitor's first organisation. `createOrganization` calls
 * `POST /api/v1/organizations/`, which is atomic end to end on the server
 * — org, Owner membership, and the three preset roles are created
 * together or not at all (organizations/services.py `create_organization`,
 * phase-3.md acceptance: "Creating an organisation is atomic ... all or
 * nothing").
 */
export default function OnboardingPage() {
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<OnboardingFormValues>();

  async function onSubmit(values: OnboardingFormValues) {
    setFormError(null);
    try {
      const organization = await createOrganization({ name: values.name });
      window.location.href = `${window.location.protocol}//${toAppHost(window.location.host)}/${organization.slug}`;
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <>
      <h1 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Create your organisation
      </h1>
      <p className="mb-6 text-sm text-neutral-600 dark:text-neutral-400">
        You&apos;ll be the Owner, and can invite teammates once it&apos;s created.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <FormField
          label="Organisation name"
          id="name"
          autoComplete="organization"
          error={errors.name?.message}
          {...register("name", { required: "Organisation name is required." })}
        />
        <SubmitButton disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create organisation"}
        </SubmitButton>
      </form>
    </>
  );
}
