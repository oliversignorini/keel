"use client";

import { applyFieldErrors } from "@/lib/api/form-error-mapper";
import { zodResolver } from "@hookform/resolvers/zod";
import { UnauthorizedError, authSignup, identitySchemas } from "@keel/api-client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { FormError } from "../_components/form-error";
import { FormField } from "../_components/form-field";
import { GoogleContinueLink } from "../_components/google-continue-link";
import { SubmitButton } from "../_components/submit-button";

type SignupFormValues = z.infer<typeof identitySchemas.authSignupBody>;

// useSearchParams() opts the page out of static rendering unless wrapped in
// its own Suspense boundary, same as /login (see that page's comment).
export default function SignupPage() {
  return (
    <Suspense>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Invitation-driven signup (PRD §6 "Invitation": "not signed in → signup,
  // prefilled + locked email, then re-resolve") — the email comes from the
  // invite page's already-resolved invitation, never typed by the visitor,
  // so it's locked rather than merely prefilled.
  const lockedEmail = searchParams.get("email");
  const next = searchParams.get("next");
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(identitySchemas.authSignupBody),
    defaultValues: lockedEmail ? { email: lockedEmail } : undefined,
  });

  async function onSubmit(values: SignupFormValues) {
    setFormError(null);
    try {
      await authSignup(values);
      router.push(next ?? "/onboarding");
    } catch (error) {
      if (error instanceof UnauthorizedError && error.code === "verify_email") {
        router.push(next ? `/verify-email?next=${encodeURIComponent(next)}` : "/verify-email");
        return;
      }
      setFormError(applyFieldErrors(error, setError));
    }
  }

  return (
    <>
      <h1 className="mb-6 text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Create an account
      </h1>
      <div className="flex flex-col gap-4">
        {lockedEmail ? null : (
          <>
            <GoogleContinueLink nextPath={next ?? "/onboarding"} />
            <div className="flex items-center gap-3 text-xs text-neutral-500">
              <div className="h-px flex-1 bg-neutral-200 dark:bg-neutral-800" />
              or
              <div className="h-px flex-1 bg-neutral-200 dark:bg-neutral-800" />
            </div>
          </>
        )}
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
          <FormError message={formError} />
          <FormField
            label="Email"
            id="email"
            type="email"
            autoComplete="email"
            error={errors.email?.message}
            readOnly={Boolean(lockedEmail)}
            aria-readonly={lockedEmail ? true : undefined}
            {...register("email")}
          />
          <FormField
            label="Password"
            id="password"
            type="password"
            autoComplete="new-password"
            error={errors.password?.message}
            {...register("password")}
          />
          <SubmitButton disabled={isSubmitting}>
            {isSubmitting ? "Creating account…" : "Sign up"}
          </SubmitButton>
        </form>
      </div>
      <p className="mt-4 text-sm text-neutral-600 dark:text-neutral-400">
        Already have an account?{" "}
        <Link href="/login" className="underline">
          Log in
        </Link>
      </p>
    </>
  );
}
