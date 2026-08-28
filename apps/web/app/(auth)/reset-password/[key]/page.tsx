"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { authPasswordReset, identitySchemas } from "@keel/api-client";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { defaultAppUrl, navigateTo } from "@/lib/navigation";

import { FormError } from "../../_components/form-error";
import { FormField } from "../../_components/form-field";
import { SubmitButton } from "../../_components/submit-button";

const passwordSchema = identitySchemas.authPasswordResetBody.pick({ password: true });
type PasswordFormValues = z.infer<typeof passwordSchema>;

export default function ResetPasswordKeyPage() {
  const router = useRouter();
  const params = useParams<{ key: string }>();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PasswordFormValues>({ resolver: zodResolver(passwordSchema) });

  async function onSubmit(values: PasswordFormValues) {
    setFormError(null);
    try {
      // See the analogous decode in verify-email/[key]/page.tsx: Next.js
      // does not decode dynamic route segments, and allauth's reset key
      // can itself contain percent-encoded characters.
      await authPasswordReset({ key: decodeURIComponent(params.key), password: values.password });
      navigateTo(router, defaultAppUrl());
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Choose a new password
      </h1>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <FormField
          label="New password"
          id="password"
          type="password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <SubmitButton disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Set new password"}
        </SubmitButton>
      </form>
    </>
  );
}
