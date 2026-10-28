"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { accountPasswordChange, identitySchemas } from "@keel/api-client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { FormError } from "../../(auth)/_components/form-error";
import { FormField } from "../../(auth)/_components/form-field";
import { SubmitButton } from "../../(auth)/_components/submit-button";
import { TotpSection } from "./totp-section";

type PasswordFormValues = z.infer<typeof identitySchemas.AccountPasswordChangeBody>;

function PasswordChangeForm() {
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PasswordFormValues>({
    resolver: zodResolver(identitySchemas.AccountPasswordChangeBody),
  });

  async function onSubmit(values: PasswordFormValues) {
    setFormError(null);
    setSuccess(false);
    try {
      await accountPasswordChange(values);
      setSuccess(true);
      reset();
    } catch (error) {
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      <FormError message={formError} />
      {success ? (
        <p className="text-sm text-green-700 dark:text-green-400">Password changed.</p>
      ) : null}
      <FormField
        label="Current password"
        id="current_password"
        type="password"
        autoComplete="current-password"
        error={errors.current_password?.message}
        {...register("current_password")}
      />
      <FormField
        label="New password"
        id="new_password"
        type="password"
        autoComplete="new-password"
        error={errors.new_password?.message}
        {...register("new_password")}
      />
      <SubmitButton disabled={isSubmitting} className="self-start">
        {isSubmitting ? "Saving…" : "Change password"}
      </SubmitButton>
    </form>
  );
}

export default function SecurityPage() {
  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4">
        <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">Password</h1>
        <PasswordChangeForm />
      </section>
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Two-factor authentication
        </h2>
        <TotpSection />
      </section>
    </div>
  );
}
