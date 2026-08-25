"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { identityFetch } from "@keel/api-client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { FormError } from "../_components/form-error";
import { FormField } from "../_components/form-field";
import { SubmitButton } from "../_components/submit-button";

// `POST /_allauth/browser/v1/auth/2fa/authenticate` only exists in the
// generated client's spec when `KEEL_MFA_ENABLED` is on at generation
// time (docs/auth-client-contract.md "MFA endpoints") — it's off by
// default (PRD §8 Phase 2: "MFA scaffolded and disabled by a settings
// flag"), so `packages/api-client` has no typed `authMfaAuthenticate` or
// `identitySchemas.authMfaAuthenticateBody` to import right now. This
// calls the same route directly through the generated transport
// (identityFetch — same CSRF handling, same typed errors) with a
// hand-written schema instead. Once the flag is on for a real project,
// `pnpm generate` produces the typed function and this file should switch
// back to it.
const mfaFormSchema = z.object({ code: z.string().min(1, "Enter your authenticator code.") });
type MfaFormValues = z.infer<typeof mfaFormSchema>;

export default function MfaChallengePage() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<MfaFormValues>({ resolver: zodResolver(mfaFormSchema) });

  async function onSubmit(values: MfaFormValues) {
    setFormError(null);
    try {
      await identityFetch("/_allauth/browser/v1/auth/2fa/authenticate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
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
