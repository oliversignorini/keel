"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, authPasswordRequest, identitySchemas } from "@keel/api-client";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { FormError } from "../_components/form-error";
import { FormField } from "../_components/form-field";
import { SubmitButton } from "../_components/submit-button";

type RequestFormValues = z.infer<typeof identitySchemas.authPasswordRequestBody>;

export default function ResetPasswordRequestPage() {
  const [formError, setFormError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RequestFormValues>({ resolver: zodResolver(identitySchemas.authPasswordRequestBody) });

  async function onSubmit(values: RequestFormValues) {
    setFormError(null);
    try {
      await authPasswordRequest(values);
      // No email-existence disclosure either way (PRD §6 Invitation applies
      // the same principle) — success is shown regardless of the outcome.
      setSent(true);
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : "Something went wrong. Try again.");
    }
  }

  if (sent) {
    return (
      <p role="status" className="text-sm text-neutral-600 dark:text-neutral-400">
        If an account exists for that email, a reset link is on its way.
      </p>
    );
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-neutral-900 dark:text-neutral-100">Reset your password</h1>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <FormField
          label="Email"
          id="email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <SubmitButton disabled={isSubmitting}>{isSubmitting ? "Sending…" : "Send reset link"}</SubmitButton>
      </form>
      <p className="mt-4 text-sm text-neutral-600 dark:text-neutral-400">
        <Link href="/login" className="underline">
          Back to login
        </Link>
      </p>
    </>
  );
}
