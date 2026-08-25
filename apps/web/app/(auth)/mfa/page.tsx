"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { authMfaAuthenticate, identitySchemas } from "@keel/api-client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { FormError } from "../_components/form-error";
import { FormField } from "../_components/form-field";
import { SubmitButton } from "../_components/submit-button";

type MfaFormValues = z.infer<typeof identitySchemas.authMfaAuthenticateBody>;

export default function MfaChallengePage() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<MfaFormValues>({ resolver: zodResolver(identitySchemas.authMfaAuthenticateBody) });

  async function onSubmit(values: MfaFormValues) {
    setFormError(null);
    try {
      await authMfaAuthenticate(values);
      router.push("/app");
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <>
      <h1 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Two-factor authentication
      </h1>
      <p className="mb-6 text-sm text-neutral-600 dark:text-neutral-400">
        Enter the 6-digit code from your authenticator app.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <FormField
          label="Code"
          id="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          error={errors.code?.message}
          {...register("code")}
        />
        <SubmitButton disabled={isSubmitting}>
          {isSubmitting ? "Verifying…" : "Verify"}
        </SubmitButton>
      </form>
    </>
  );
}
